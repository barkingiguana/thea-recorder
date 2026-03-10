package com.recorder;

/**
 * Metadata about a stored recording.
 *
 * @param name    the recording name
 * @param path    the file path on the server
 * @param size    file size in bytes
 * @param created creation timestamp string
 */
public record RecordingInfo(String name, String path, long size, String created) {
}
