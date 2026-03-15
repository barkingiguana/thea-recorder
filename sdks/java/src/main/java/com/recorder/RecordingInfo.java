package com.recorder;

import java.util.List;

/**
 * Metadata about a stored recording.
 *
 * @param name              the recording name
 * @param path              the file path on the server
 * @param size              file size in bytes
 * @param created           creation timestamp string
 * @param gif_path          path to the GIF file (null if not available)
 * @param gif_size          GIF file size in bytes (0 if not available)
 * @param webm_path         path to the WebM file (null if not available)
 * @param webm_size         WebM file size in bytes (0 if not available)
 * @param formats_available list of available output formats (null if not reported)
 */
public record RecordingInfo(String name, String path, long size, String created,
                            String gif_path, long gif_size,
                            String webm_path, long webm_size,
                            List<String> formats_available) {

    /**
     * Backwards-compatible constructor without GIF/WebM fields.
     */
    public RecordingInfo(String name, String path, long size, String created) {
        this(name, path, size, created, null, 0, null, 0, null);
    }
}
