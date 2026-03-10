package com.recorder;

/**
 * A display panel.
 *
 * @param name  panel identifier
 * @param title panel title
 * @param width panel width in characters
 */
public record Panel(String name, String title, int width) {
}
