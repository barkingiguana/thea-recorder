# frozen_string_literal: true

require_relative "lib/recorder"

Gem::Specification.new do |spec|
  spec.name          = "thea-recorder"
  spec.version       = Recorder::VERSION
  spec.authors       = ["Mechanical Rock"]
  spec.email         = ["info@mechanicalrock.io"]

  spec.summary       = "Ruby SDK for the thea-recorder HTTP server"
  spec.description   = "A lightweight Ruby client for driving the thea-recorder " \
                        "virtual display and screen recording server. Uses only " \
                        "Ruby stdlib (net/http) with zero runtime dependencies."
  spec.homepage      = "https://github.com/BarkingIguana/thea-recorder"
  spec.license       = "MIT"

  spec.required_ruby_version = ">= 2.6"

  spec.files         = ["lib/recorder.rb"]
  spec.require_paths = ["lib"]

  spec.add_development_dependency "minitest", "~> 5.0"
  spec.add_development_dependency "webmock", "~> 3.0"
  spec.add_development_dependency "rake", "~> 13.0"
end
