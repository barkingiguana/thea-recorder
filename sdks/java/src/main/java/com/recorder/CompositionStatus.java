package com.recorder;

/**
 * Status of a composition.
 *
 * @param name       the composition name
 * @param status     the current status (e.g. "pending", "processing", "complete", "failed")
 * @param outputPath the output file path on the server
 * @param error      error message if the composition failed
 */
public record CompositionStatus(String name, String status, String outputPath, String error) {
}
