package com.recorder;

import java.util.List;

/**
 * Server health status.
 *
 * @param status    health status string (e.g. "ok")
 * @param recording whether a recording is in progress
 * @param display   display string (e.g. ":99") or empty if not started
 * @param panels    list of active panel names
 * @param uptime    server uptime in seconds
 */
public record Health(String status, boolean recording, String display, List<String> panels, double uptime) {
}
