package com.recorder;

/**
 * Current recording status.
 *
 * @param recording whether a recording is in progress
 * @param name      the current recording name, or null if not recording
 * @param elapsed   elapsed time in seconds, or 0 if not recording
 */
public record RecordingStatus(boolean recording, String name, double elapsed) {
}
