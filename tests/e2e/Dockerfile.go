FROM golang:1.21-alpine

WORKDIR /app
COPY sdks/go/go.mod .
COPY sdks/go/thea/ thea/

# Create a cmd directory for the e2e test
RUN mkdir -p cmd/e2e
COPY tests/e2e/test_e2e.go cmd/e2e/main.go

RUN cd cmd/e2e && go build -o /test_e2e .
CMD ["/test_e2e"]
