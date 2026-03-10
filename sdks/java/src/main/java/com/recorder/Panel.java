package com.recorder;

/**
 * A display panel.
 *
 * @param name   panel identifier
 * @param title  panel title
 * @param width  panel width in characters
 * @param height panel height in lines (0 if not set)
 */
public record Panel(String name, String title, int width, int height) {
}
