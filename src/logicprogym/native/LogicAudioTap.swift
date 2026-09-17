// Native Core Audio process capture, macOS 14.2+. No loopback driver required.
// stdout: one JSON format line, then fixed 512-byte DGA1 PCM packets.
// stderr: diagnostics only. stdin EOF, SIGINT, or SIGTERM releases the tap.
import Foundation
import AppKit
import CoreAudio
import AudioToolbox
import Darwin

struct CaptureError: Error, CustomStringConvertible {
    let description: String
    init(_ message: String) { description = message }
}

func checked(_ status: OSStatus, _ operation: String) throws {
    if status != noErr { throw CaptureError("\(operation) failed (Core Audio \(status)). Check system audio recording permission in macOS Settings.") }
}

func propertyAddress(_ selector: AudioObjectPropertySelector) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal,
                               mElement: kAudioObjectPropertyElementMain)
}

// A preallocated packet avoids allocation and blocking I/O in the audio callback.
// PIPE_BUF is 512 bytes on macOS: writes are atomic or dropped when the pipe is full.
final class PacketWriter {
    let packet = UnsafeMutableRawPointer.allocate(byteCount: 512, alignment: 8)
    var sequence: UInt32 = 0
    init() { packet.initializeMemory(as: UInt8.self, repeating: 0, count: 512) }
    deinit { packet.deallocate() }

    func emit(_ input: UnsafePointer<AudioBufferList>) {
        let buffers = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: input))
        guard let first = buffers.first, first.mData != nil else { return }
        let interleaved = buffers.count == 1 && first.mNumberChannels == 2
        guard interleaved || (buffers.count == 2 && buffers[0].mNumberChannels == 1 && buffers[1].mNumberChannels == 1 && buffers[1].mData != nil) else { return }
        let frames = interleaved ? Int(first.mDataByteSize) / 8 : min(Int(first.mDataByteSize), Int(buffers[1].mDataByteSize)) / 4
        let left = first.mData!.assumingMemoryBound(to: Float.self)
        let right = interleaved ? left : buffers[1].mData!.assumingMemoryBound(to: Float.self)
        var offset = 0
        while offset < frames {
            let count = min(62, frames - offset)
            packet.storeBytes(of: UInt32(0x31414744).littleEndian, as: UInt32.self) // DGA1
            packet.storeBytes(of: sequence.littleEndian, toByteOffset: 4, as: UInt32.self)
            packet.storeBytes(of: UInt32(count).littleEndian, toByteOffset: 8, as: UInt32.self)
            packet.storeBytes(of: UInt32(0), toByteOffset: 12, as: UInt32.self)
            let samples = packet.advanced(by: 16).assumingMemoryBound(to: Float.self)
            for index in 0..<count {
                samples[2 * index] = left[interleaved ? 2 * (offset + index) : offset + index]
                samples[2 * index + 1] = right[interleaved ? 2 * (offset + index) + 1 : offset + index]
            }
            // A missing sequence tells Python to invalidate the previous window.
            _ = Darwin.write(STDOUT_FILENO, packet, 512)
            sequence &+= 1
            offset += count
        }
    }
}

@available(macOS 14.2, *)
func capture(bundleID: String) throws {
    let apps = NSRunningApplication.runningApplications(withBundleIdentifier: bundleID)
    guard apps.count == 1, let app = apps.first else {
        throw CaptureError("Expected one running application with bundle ID \(bundleID); found \(apps.count). Open Logic first.")
    }
    var pid = app.processIdentifier
    var processID = AudioObjectID(kAudioObjectUnknown)
    var address = propertyAddress(kAudioHardwarePropertyTranslatePIDToProcessObject)
    var size = UInt32(MemoryLayout<AudioObjectID>.size)
    try checked(AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address,
        UInt32(MemoryLayout<pid_t>.size), &pid, &size, &processID), "Resolve application audio")
    guard processID != kAudioObjectUnknown else { throw CaptureError("Logic has no Core Audio process yet. Enable audio in Logic and play a sound first.") }

    let description = CATapDescription(stereoMixdownOfProcesses: [processID])
    description.name = "LogicProGym Logic audio"
    description.uuid = UUID()
    description.isPrivate = true
    description.muteBehavior = .unmuted
    var tap = AudioObjectID(kAudioObjectUnknown)
    try checked(AudioHardwareCreateProcessTap(description, &tap), "Create process tap")
    defer { AudioHardwareDestroyProcessTap(tap) }

    var format = AudioStreamBasicDescription()
    address = propertyAddress(kAudioTapPropertyFormat)
    size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
    try checked(AudioObjectGetPropertyData(tap, &address, 0, nil, &size, &format), "Read tap format")
    guard format.mFormatID == kAudioFormatLinearPCM,
          format.mFormatFlags & kAudioFormatFlagIsFloat != 0,
          format.mFormatFlags & kAudioFormatFlagIsBigEndian == 0,
          format.mBitsPerChannel == 32, format.mChannelsPerFrame == 2,
          format.mSampleRate > 0 else { throw CaptureError("Unsupported tap format; expected float32 stereo PCM.") }

    let aggregateSpec: [String: Any] = [
        kAudioAggregateDeviceNameKey: "LogicProGym private capture",
        kAudioAggregateDeviceUIDKey: UUID().uuidString,
        kAudioAggregateDeviceIsPrivateKey: true,
        kAudioAggregateDeviceTapAutoStartKey: true,
        kAudioAggregateDeviceTapListKey: [[kAudioSubTapUIDKey: description.uuid.uuidString,
                                          kAudioSubTapDriftCompensationKey: true]]
    ]
    var device = AudioObjectID(kAudioObjectUnknown)
    try checked(AudioHardwareCreateAggregateDevice(aggregateSpec as CFDictionary, &device), "Create private capture device")
    defer { AudioHardwareDestroyAggregateDevice(device) }

    let writer = PacketWriter()
    var ioProc: AudioDeviceIOProcID?
    try checked(AudioDeviceCreateIOProcIDWithBlock(&ioProc, device, nil) { _, input, _, _, _ in
        writer.emit(input)
    }, "Create capture callback")
    defer { if let ioProc { AudioDeviceDestroyIOProcID(device, ioProc) } }

    // Format is emitted before PCM. Python's reader is ready before the tap starts.
    let header: [String: Any] = ["protocol": 1, "sample_rate": format.mSampleRate,
                               "channels": 2, "bundle_id": bundleID, "pid": pid]
    let json = try JSONSerialization.data(withJSONObject: header)
    FileHandle.standardOutput.write(json)
    FileHandle.standardOutput.write(Data([10]))
    signal(SIGPIPE, SIG_IGN)
    let flags = fcntl(STDOUT_FILENO, F_GETFL)
    guard flags >= 0, fcntl(STDOUT_FILENO, F_SETFL, flags | O_NONBLOCK) >= 0 else {
        throw CaptureError("Cannot configure nonblocking PCM output")
    }

    let stopped = DispatchSemaphore(value: 0)
    signal(SIGTERM, SIG_IGN)
    signal(SIGINT, SIG_IGN)
    let terminate = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .global())
    let interrupt = DispatchSource.makeSignalSource(signal: SIGINT, queue: .global())
    terminate.setEventHandler { stopped.signal() }
    interrupt.setEventHandler { stopped.signal() }
    terminate.resume(); interrupt.resume()
    defer { terminate.cancel(); interrupt.cancel() }
    DispatchQueue.global().async {
        var byte: UInt8 = 0
        // stdin belongs to the Python parent. EOF also handles parent SIGKILL.
        while Darwin.read(STDIN_FILENO, &byte, 1) > 0 {}
        stopped.signal()
    }
    try checked(AudioDeviceStart(device, ioProc), "Start audio capture")
    defer { AudioDeviceStop(device, ioProc) }
    while stopped.wait(timeout: .now() + 1) == .timedOut {
        if app.isTerminated { throw CaptureError("The captured application exited") }
        var current = AudioStreamBasicDescription()
        var currentAddress = propertyAddress(kAudioTapPropertyFormat)
        var currentSize = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        try checked(AudioObjectGetPropertyData(tap, &currentAddress, 0, nil, &currentSize, &current), "Check tap format")
        if current.mSampleRate != format.mSampleRate || current.mChannelsPerFrame != format.mChannelsPerFrame || current.mFormatID != format.mFormatID || current.mFormatFlags != format.mFormatFlags {
            throw CaptureError("Audio format changed. Restart capture to use Logic's new audio settings.")
        }
    }
}

do {
    let args = Array(CommandLine.arguments.dropFirst())
    if args == ["--help"] {
        print("LogicProGym native audio helper: --bundle-id com.apple.logic10; --list lists running apps. Requires macOS 14.2+.")
    } else if args == ["--list"] {
        let apps = NSWorkspace.shared.runningApplications.compactMap { app -> [String: Any]? in
            guard let id = app.bundleIdentifier else { return nil }
            return ["bundle_id": id, "name": app.localizedName ?? id, "pid": app.processIdentifier]
        }
        FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: apps, options: [.prettyPrinted, .sortedKeys]))
    } else if args.count == 2 && args[0] == "--bundle-id" {
        if #available(macOS 14.2, *) { try capture(bundleID: args[1]) }
        else { throw CaptureError("Native audio capture requires macOS 14.2 or later") }
    } else { throw CaptureError("Use --help, --list, or --bundle-id APPLICATION_ID") }
} catch {
    FileHandle.standardError.write(Data("\(error)\n".utf8))
    exit(1)
}
