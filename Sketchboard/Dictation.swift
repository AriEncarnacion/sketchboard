import AVFoundation
import Speech
import SwiftUI

/// Microphone → text. Wraps SFSpeechRecognizer + AVAudioEngine so a mic button can fill any
/// text field with the same string the keyboard would have produced. Partial results stream
/// in while you talk; whatever was heard stays in the field after you stop.
///
/// One instance is shared by every button, so starting a second field stops the first —
/// two AVAudioEngines fighting over the mic would fail anyway.
@Observable
final class Dictation {
    /// Which field is recording, nil when idle. Buttons compare against their own key.
    private(set) var activeField: String?
    private(set) var errorMessage: String?

    private let recognizer = SFSpeechRecognizer(locale: Locale.current)
        ?? SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private let engine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var prefix = ""
    private var tapped = false

    func isRecording(_ field: String) -> Bool { activeField == field }

    var isSupported: Bool { recognizer != nil }

    /// Starts dictating into `text`, or stops if this field is the one already running.
    func toggle(field: String, text: Binding<String>) {
        if activeField == field { stop(); return }
        if activeField != nil { stop() }
        start(field: field, text: text)
    }

    func stop() {
        guard activeField != nil else { return }
        activeField = nil
        teardownAudio()
        request?.endAudio()   // lets the task deliver one last result before it finishes
    }

    // MARK: Internals

    private func start(field: String, text: Binding<String>) {
        errorMessage = nil
        requestAccess { [weak self] granted in
            guard let self else { return }
            guard granted else {
                self.errorMessage = "Allow microphone and speech recognition in Settings to dictate."
                return
            }
            do { try self.beginSession(field: field, text: text) }
            catch {
                self.errorMessage = error.localizedDescription
                self.finish()
            }
        }
    }

    /// Speech recognition and mic access are separate grants; both are required.
    private func requestAccess(_ done: @escaping (Bool) -> Void) {
        SFSpeechRecognizer.requestAuthorization { status in
            guard status == .authorized else {
                DispatchQueue.main.async { done(false) }
                return
            }
            AVAudioApplication.requestRecordPermission { granted in
                DispatchQueue.main.async { done(granted) }
            }
        }
    }

    private func beginSession(field: String, text: Binding<String>) throws {
        guard let recognizer, recognizer.isAvailable else {
            errorMessage = "Speech recognition is unavailable right now."
            return
        }

        let audio = AVAudioSession.sharedInstance()
        try audio.setCategory(.record, mode: .measurement, options: .duckOthers)
        try audio.setActive(true, options: .notifyOthersOnDeactivation)

        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        // Keeps the audio on the iPad when the model supports it.
        req.requiresOnDeviceRecognition = recognizer.supportsOnDeviceRecognition
        request = req

        let input = engine.inputNode
        input.installTap(onBus: 0, bufferSize: 1024, format: input.outputFormat(forBus: 0)) { buffer, _ in
            req.append(buffer)
        }
        tapped = true
        engine.prepare()
        try engine.start()

        // Dictation adds to whatever is already typed rather than replacing it.
        let existing = text.wrappedValue.trimmingCharacters(in: .whitespaces)
        prefix = existing.isEmpty ? "" : existing + " "
        activeField = field

        task = recognizer.recognitionTask(with: req) { [weak self] result, error in
            guard let self else { return }
            if let result {
                let heard = result.bestTranscription.formattedString
                DispatchQueue.main.async { text.wrappedValue = self.prefix + heard }
            }
            if error != nil || result?.isFinal == true {
                DispatchQueue.main.async {
                    // A cancelled task reports an error; that's an ordinary stop, not a failure.
                    if let error, self.activeField != nil { self.errorMessage = error.localizedDescription }
                    self.finish()
                }
            }
        }
    }

    private func finish() {
        activeField = nil
        teardownAudio()
        request = nil
        task = nil
    }

    private func teardownAudio() {
        if engine.isRunning { engine.stop() }
        if tapped {
            engine.inputNode.removeTap(onBus: 0)
            tapped = false
        }
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
}

/// Mic button that fills the field next to it. `field` just has to be unique per text input.
struct DictationButton: View {
    let dictation: Dictation
    let field: String
    @Binding var text: String
    var isEnabled = true

    var body: some View {
        let recording = dictation.isRecording(field)
        Button {
            dictation.toggle(field: field, text: $text)
        } label: {
            Image(systemName: recording ? "mic.fill" : "mic")
                .symbolEffect(.pulse, isActive: recording)
        }
        .buttonStyle(.bordered)
        .tint(recording ? .red : nil)
        .disabled(!isEnabled || !dictation.isSupported)
        .accessibilityLabel(recording ? "Stop dictation" : "Dictate")
    }
}
