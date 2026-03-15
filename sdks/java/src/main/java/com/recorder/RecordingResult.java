package com.recorder;

import java.util.Map;

/**
 * Result returned when a recording is stopped.
 *
 * @param name       the recording name
 * @param path       the file path on the server
 * @param elapsed    elapsed time in seconds
 * @param gif_path   path to the generated GIF file (null if not requested)
 * @param extra_paths additional output paths keyed by format (null if none)
 */
public record RecordingResult(String name, String path, double elapsed,
                              String gif_path, Map<String, String> extra_paths) {

    /**
     * Backwards-compatible constructor without GIF fields.
     */
    public RecordingResult(String name, String path, double elapsed) {
        this(name, path, elapsed, null, null);
    }
}
