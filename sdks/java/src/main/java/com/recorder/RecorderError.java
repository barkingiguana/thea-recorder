package com.recorder;

/**
 * Exception thrown when the recorder server returns an error or a request fails.
 */
public class RecorderError extends RuntimeException {

    private final int statusCode;

    public RecorderError(String message) {
        super(message);
        this.statusCode = -1;
    }

    public RecorderError(String message, Throwable cause) {
        super(message, cause);
        this.statusCode = -1;
    }

    public RecorderError(int statusCode, String message) {
        super(message);
        this.statusCode = statusCode;
    }

    /**
     * Returns the HTTP status code, or -1 if the error was not from an HTTP response.
     */
    public int getStatusCode() {
        return statusCode;
    }
}
