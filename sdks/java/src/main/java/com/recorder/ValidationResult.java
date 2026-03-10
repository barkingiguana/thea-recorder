package com.recorder;

import java.util.List;

/**
 * Result of a layout validation check.
 *
 * @param valid    whether the layout is valid
 * @param warnings list of warning messages (may be empty)
 */
public record ValidationResult(boolean valid, List<String> warnings) {
}
