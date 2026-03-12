package thea

import "net/http"

// IsConflict reports whether err is a RecorderError with HTTP 409 Conflict.
// This typically means the resource already exists (e.g. a recording is
// already in progress).
func IsConflict(err error) bool {
	e, ok := err.(*RecorderError)
	return ok && e.StatusCode == http.StatusConflict
}

// IsAccepted reports whether err is a RecorderError with HTTP 202 Accepted.
// This occurs when an asynchronous operation has been accepted but is not yet
// complete (e.g. a composition is still rendering).
func IsAccepted(err error) bool {
	e, ok := err.(*RecorderError)
	return ok && e.StatusCode == http.StatusAccepted
}

// IsNotFound reports whether err is a RecorderError with HTTP 404 Not Found.
func IsNotFound(err error) bool {
	e, ok := err.(*RecorderError)
	return ok && e.StatusCode == http.StatusNotFound
}
