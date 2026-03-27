"""Tests for MET-1086: enum parameter validation errors should report
the correct parameter name, not the enum value, as the field name.

When a query parameter like ``interval`` (with enum: [day]) receives an
invalid value like ``week``, the error response should identify the
field as ``interval`` — not ``day`` (the enum value).
"""

import pytest

from openapi_core import validate_request
from openapi_core.testing import MockRequest
from openapi_core.unmarshalling.request.unmarshallers import (
    V30RequestUnmarshaller,
)
from openapi_core.validation.request.exceptions import InvalidParameter
from openapi_core.validation.request.exceptions import ParameterValidationError
from openapi_core.validation.schemas.exceptions import InvalidSchemaValue


class TestEnumParameterValidationError:
    """Validates that enum validation errors correctly identify the
    parameter name at the validation/unmarshalling level."""

    host_url = "https://api.example.com"
    spec_path = "data/v3.0/enum_param.yaml"

    @pytest.fixture(scope="class")
    def spec(self, schema_path_factory):
        return schema_path_factory.from_file(self.spec_path)

    @pytest.fixture(scope="class")
    def request_unmarshaller(self, spec):
        return V30RequestUnmarshaller(spec)

    def _make_request(self, args):
        return MockRequest(
            self.host_url,
            "GET",
            "/metrics/mrr-change",
            path_pattern="/metrics/mrr-change",
            args=args,
        )

    def test_valid_enum_value_passes(self, request_unmarshaller):
        """Sanity check: valid enum value should not produce errors."""
        request = self._make_request({
            "interval": "day",
            "from": "2026-01-01T00:00:00Z",
            "to": "2026-03-06T00:00:00Z",
        })

        result = request_unmarshaller.unmarshal(request)

        assert result.errors == []

    def test_invalid_enum_raises_invalid_parameter_with_name(
        self, request_unmarshaller
    ):
        """When an enum parameter receives an invalid value, the resulting
        InvalidParameter error must carry the parameter name, not the
        enum value."""
        request = self._make_request({
            "interval": "week",
            "from": "2026-01-01T00:00:00Z",
            "to": "2026-03-06T00:00:00Z",
        })

        result = request_unmarshaller.unmarshal(request)

        assert len(result.errors) == 1
        error = result.errors[0]
        assert isinstance(error, InvalidParameter)
        assert error.name == "interval"
        assert error.location == "query"


_HANDLER_PARAMS = [
    pytest.param(
        "openapi_core.contrib.flask.handlers",
        "FlaskOpenAPIErrorsHandler",
        id="flask",
    ),
    pytest.param(
        "openapi_core.contrib.django.handlers",
        "DjangoOpenAPIErrorsHandler",
        id="django",
    ),
    pytest.param(
        "openapi_core.contrib.starlette.handlers",
        "StarletteOpenAPIErrorsHandler",
        id="starlette",
    ),
    pytest.param(
        "openapi_core.contrib.falcon.handlers",
        "FalconOpenAPIErrorsHandler",
        id="falcon",
    ),
]


class TestEnumParameterErrorHandler:
    """Validates that the contrib error handlers preserve the parameter
    name when formatting enum validation errors.

    This is the public contract that MET-1086 is about: when the
    formatted error reaches consumers, the parameter name (``interval``)
    must be present — not just the enum value (``day``).
    """

    host_url = "https://api.example.com"
    spec_path = "data/v3.0/enum_param.yaml"

    @pytest.fixture(scope="class")
    def spec(self, schema_path_factory):
        return schema_path_factory.from_file(self.spec_path)

    @pytest.fixture(scope="class")
    def request_unmarshaller(self, spec):
        return V30RequestUnmarshaller(spec)

    def _make_request(self, args):
        return MockRequest(
            self.host_url,
            "GET",
            "/metrics/mrr-change",
            path_pattern="/metrics/mrr-change",
            args=args,
        )

    def _get_real_error(self, request_unmarshaller, args):
        """Run a real validation to get the actual error chain rather
        than constructing one by hand."""
        request = self._make_request(args)
        result = request_unmarshaller.unmarshal(request)
        assert len(result.errors) == 1
        return result.errors[0]

    @pytest.mark.parametrize("module_path,cls_name", _HANDLER_PARAMS)
    def test_handler_formatted_error_contains_parameter_name(
        self, request_unmarshaller, module_path, cls_name
    ):
        """The formatted error produced by each contrib handler must
        contain the parameter name 'interval', so that consumers can
        identify which field failed validation.
        """
        import importlib

        handler_module = importlib.import_module(module_path)
        handler_cls = getattr(handler_module, cls_name)

        error = self._get_real_error(
            request_unmarshaller,
            {
                "interval": "week",
                "from": "2026-01-01T00:00:00Z",
                "to": "2026-03-06T00:00:00Z",
            },
        )

        formatted = handler_cls.format_openapi_error(error)

        assert "interval" in formatted["title"], (
            f"Formatted error title should contain the parameter name "
            f"'interval', but got: {formatted['title']!r}"
        )

    @pytest.mark.parametrize("module_path,cls_name", _HANDLER_PARAMS)
    def test_handler_formatted_error_contains_multi_value_enum_parameter_name(
        self, request_unmarshaller, module_path, cls_name
    ):
        """Same contract for a parameter with multiple enum values:
        the formatted error must name 'granularity', not any of the
        allowed values (day, week, month).
        """
        import importlib

        handler_module = importlib.import_module(module_path)
        handler_cls = getattr(handler_module, cls_name)

        error = self._get_real_error(
            request_unmarshaller,
            {
                "interval": "day",
                "granularity": "year",
                "from": "2026-01-01T00:00:00Z",
                "to": "2026-03-06T00:00:00Z",
            },
        )

        formatted = handler_cls.format_openapi_error(error)

        assert "granularity" in formatted["title"], (
            f"Formatted error title should contain the parameter name "
            f"'granularity', but got: {formatted['title']!r}"
        )
