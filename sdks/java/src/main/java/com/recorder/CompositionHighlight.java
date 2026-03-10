package com.recorder;

/**
 * A highlight to apply to a composition.
 *
 * @param recording the recording name to highlight
 * @param time      the start time in seconds
 * @param duration  the duration in seconds
 */
public record CompositionHighlight(String recording, double time, double duration) {
}
