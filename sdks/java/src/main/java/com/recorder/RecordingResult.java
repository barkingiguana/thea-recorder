package com.recorder;

/**
 * Result returned when a recording is stopped.
 *
 * @param name    the recording name
 * @param path    the file path on the server
 * @param elapsed elapsed time in seconds
 */
public record RecordingResult(String name, String path, double elapsed) {
}
