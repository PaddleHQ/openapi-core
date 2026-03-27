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
    """Validates that enum validation errors correctly identify the parameter name."""

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

    def test_invalid_enum_raises_invalid_parameter(self, request_unmarshaller):
        """InvalidParameter should be raised with the correct parameter name."""
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

    def test_invalid_enum_cause_is_invalid_schema_value(
        self, request_unmarshaller
    ):
        """The __cause__ of InvalidParameter should be InvalidSchemaValue."""
        request = self._make_request({
            "interval": "week",
            "from": "2026-01-01T00:00:00Z",
            "to": "2026-03-06T00:00:00Z",
        })

        result = request_unmarshaller.unmarshal(request)

        error = result.errors[0]
        assert isinstance(error.__cause__, InvalidSchemaValue)
        assert len(error.__cause__.schema_errors) == 1
        schema_error = error.__cause__.schema_errors[0]
        assert "'week' is not one of ['day']" in schema_error.message

    def test_invalid_enum_error_str_contains_parameter_name(
        self, request_unmarshaller
    ):
        """str(InvalidParameter) should contain the parameter name."""
        request = self._make_request({
            "interval": "week",
            "from": "2026-01-01T00:00:00Z",
            "to": "2026-03-06T00:00:00Z",
        })

        result = request_unmarshaller.unmarshal(request)

        error = result.errors[0]
        assert "interval" in str(error)

    def test_invalid_enum_cause_str_does_not_use_enum_value_as_field(
        self, request_unmarshaller
    ):
        """The __cause__ string should not mislead consumers into using the
        enum value ('day') as the field name. It should reference the
        parameter name ('interval') instead.

        This is the core of the MET-1086 bug: when ``format_openapi_error``
        unwraps to ``__cause__``, the parameter name is lost and consumers
        end up extracting the enum value as the field.
        """
        request = self._make_request({
            "interval": "week",
            "from": "2026-01-01T00:00:00Z",
            "to": "2026-03-06T00:00:00Z",
        })

        result = request_unmarshaller.unmarshal(request)

        error = result.errors[0]
        cause = error.__cause__
        assert isinstance(cause, InvalidSchemaValue)

        cause_str = str(cause)
        assert "interval" in cause_str, (
            f"InvalidSchemaValue string should contain the parameter name "
            f"'interval', but got: {cause_str!r}"
        )

    def test_invalid_enum_schema_error_path_identifies_parameter(
        self, request_unmarshaller
    ):
        """The jsonschema ValidationError on enum failure should provide
        enough context to identify the parameter name. Currently, the path
        is empty and the validator_value contains the enum values, which
        causes consumers to mistake enum values for field names.
        """
        request = self._make_request({
            "interval": "week",
            "from": "2026-01-01T00:00:00Z",
            "to": "2026-03-06T00:00:00Z",
        })

        result = request_unmarshaller.unmarshal(request)

        error = result.errors[0]
        cause = error.__cause__
        schema_error = cause.schema_errors[0]

        assert schema_error.validator_value == ["day"]
        assert list(schema_error.path) == [], (
            "Expected empty path for enum validation at root level"
        )

        # BUG: validator_value[0] is 'day' (the enum value), not 'interval'
        # (the parameter name). Consumers who fall back to validator_value[0]
        # as a field name will get the wrong result.
        field_from_validator_value = schema_error.validator_value[0]
        assert field_from_validator_value != "interval", (
            "validator_value[0] should not be 'interval' — this is the enum "
            "value, confirming the bug source"
        )

    def test_multiple_enum_values_wrong_field(self, request_unmarshaller):
        """When a parameter has multiple enum values (e.g., granularity with
        [day, week, month]), passing an invalid value should report the
        parameter name 'granularity', not any enum value.
        """
        request = self._make_request({
            "interval": "day",
            "granularity": "year",
            "from": "2026-01-01T00:00:00Z",
            "to": "2026-03-06T00:00:00Z",
        })

        result = request_unmarshaller.unmarshal(request)

        assert len(result.errors) == 1
        error = result.errors[0]
        assert isinstance(error, InvalidParameter)
        assert error.name == "granularity"
        assert error.location == "query"

        cause = error.__cause__
        assert isinstance(cause, InvalidSchemaValue)
        cause_str = str(cause)
        assert "granularity" in cause_str, (
            f"InvalidSchemaValue string should contain the parameter name "
            f"'granularity', but got: {cause_str!r}"
        )

    def test_validate_request_invalid_enum_reports_parameter_name(self, spec):
        """validate_request should raise ParameterValidationError with
        the correct parameter name for enum violations.
        """
        request = self._make_request({
            "interval": "week",
            "from": "2026-01-01T00:00:00Z",
            "to": "2026-03-06T00:00:00Z",
        })

        with pytest.raises(ParameterValidationError) as exc_info:
            validate_request(request, spec=spec)

        assert exc_info.value.name == "interval"
        assert exc_info.value.location == "query"


class TestEnumParameterErrorHandler:
    """Validates that the contrib error handlers preserve the parameter
    name when formatting enum validation errors.

    All four contrib handlers (Flask, Django, Starlette, Falcon) share
    the same pattern: they unwrap ``error.__cause__`` before formatting,
    which loses the parameter name from ``InvalidParameter``.
    """

    def _make_invalid_parameter_error(self):
        """Simulate the error chain produced by enum validation failure:
        InvalidParameter(name='interval', location='query')
          -- __cause__: InvalidSchemaValue(...)
        """
        from jsonschema.exceptions import (
            ValidationError as JsonSchemaValidationError,
        )

        schema_error = JsonSchemaValidationError(
            "'week' is not one of ['day']",
            validator="enum",
            validator_value=["day"],
            instance="week",
            schema={"type": "string", "enum": ["day"]},
        )
        cause = InvalidSchemaValue(
            value="week",
            type="string",
            schema_errors=(schema_error,),
        )
        try:
            raise cause
        except InvalidSchemaValue:
            error = InvalidParameter(name="interval", location="query")
            error.__cause__ = cause
        return error

    def test_flask_handler_preserves_parameter_name(self):
        """Flask error handler should include the parameter name 'interval'
        in the formatted error, not just the InvalidSchemaValue string.
        """
        from openapi_core.contrib.flask.handlers import (
            FlaskOpenAPIErrorsHandler,
        )

        error = self._make_invalid_parameter_error()
        formatted = FlaskOpenAPIErrorsHandler.format_openapi_error(error)

        assert "interval" in formatted["title"], (
            f"Formatted error title should contain 'interval', "
            f"but got: {formatted['title']!r}"
        )

    def test_django_handler_preserves_parameter_name(self):
        """Django error handler should include the parameter name 'interval'
        in the formatted error.
        """
        from openapi_core.contrib.django.handlers import (
            DjangoOpenAPIErrorsHandler,
        )

        error = self._make_invalid_parameter_error()
        formatted = DjangoOpenAPIErrorsHandler.format_openapi_error(error)

        assert "interval" in formatted["title"], (
            f"Formatted error title should contain 'interval', "
            f"but got: {formatted['title']!r}"
        )

    def test_starlette_handler_preserves_parameter_name(self):
        """Starlette error handler should include the parameter name
        'interval' in the formatted error.
        """
        from openapi_core.contrib.starlette.handlers import (
            StarletteOpenAPIErrorsHandler,
        )

        error = self._make_invalid_parameter_error()
        formatted = StarletteOpenAPIErrorsHandler.format_openapi_error(error)

        assert "interval" in formatted["title"], (
            f"Formatted error title should contain 'interval', "
            f"but got: {formatted['title']!r}"
        )

    def test_falcon_handler_preserves_parameter_name(self):
        """Falcon error handler should include the parameter name 'interval'
        in the formatted error.
        """
        from openapi_core.contrib.falcon.handlers import (
            FalconOpenAPIErrorsHandler,
        )

        error = self._make_invalid_parameter_error()
        formatted = FalconOpenAPIErrorsHandler.format_openapi_error(error)

        assert "interval" in formatted["title"], (
            f"Formatted error title should contain 'interval', "
            f"but got: {formatted['title']!r}"
        )
