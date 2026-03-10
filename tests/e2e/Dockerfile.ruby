FROM ruby:3.2-slim

WORKDIR /app
COPY sdks/ruby/lib/ lib/
COPY tests/e2e/test_e2e.rb .

CMD ["ruby", "test_e2e.rb"]
