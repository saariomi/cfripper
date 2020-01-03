import logging
import sys
from io import TextIOWrapper
from itertools import chain
from pathlib import Path
from typing import Dict, Optional

import click
import pycfmodel
from pycfmodel.model.cf_model import CFModel

from cfripper.__version__ import __version__
from cfripper.config.config import Config
from cfripper.model.result import Result
from cfripper.model.utils import convert_json_or_yaml_to_dict
from cfripper.rule_processor import RuleProcessor
from cfripper.rules import DEFAULT_RULES

LOGGING_LEVELS = {
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def setup_logging(level: str) -> None:
    logging.basicConfig(level=LOGGING_LEVELS[level], format="%(message)s")


def get_cfmodel(template: TextIOWrapper) -> CFModel:
    template = convert_json_or_yaml_to_dict(template.read())
    cfmodel = pycfmodel.parse(template)
    return cfmodel


def process_template(
    template, resolve: bool, resolve_parameters: Optional[Dict], output_folder: Optional[str], output_format: str
) -> None:
    logging.info(f"Analysing {template.name}...")
    cfmodel = get_cfmodel(template)
    if resolve:
        cfmodel = cfmodel.resolve(resolve_parameters)
    config = Config(rules=DEFAULT_RULES.keys())
    result = Result()
    rules = [DEFAULT_RULES.get(rule)(config, result) for rule in config.rules]
    rule_processor = RuleProcessor(*rules)

    rule_processor.process_cf_template(cfmodel, config, result)

    if output_format == "json":
        formatted_result = result.json()
    else:
        result_lines = []
        result_lines.append(f"Valid: {result.valid}")
        if result.failed_rules:
            result_lines.append("Issues found:")
            [result_lines.append(f"\t- {r.rule}: {r.reason}") for r in result.failed_rules]
        if result.failed_monitored_rules:
            result_lines.append("Monitored issues found:")
            [result_lines.append(f"\t- {r.rule}: {r.reason}") for r in result.failed_monitored_rules]
        formatted_result = "\n".join(result_lines)

    if output_folder:
        output_file = Path(output_folder) / f"{template.name}.cfripper.results.{output_format}"
        output_file.write_text(formatted_result)
        logging.info(f"Result saved in {output_file}")
    else:
        click.echo(formatted_result)


@click.command()
@click.version_option(prog_name="cfripper", version=__version__)
@click.argument("templates", type=click.File("r"), nargs=-1)
@click.option(
    "--resolve/--no-resolve",
    is_flag=True,
    default=False,
    help="Resolves cloudformation intrinsic functions",
    show_default=True,
)
@click.option(
    "--resolve-parameters",
    type=click.File("r"),
    help=(
        "JSON/YML file containing key-value pairs used for resolving CloudFormation files with templated parameters. "
        'For example, {"abc": "ABC"} will change all occurrences of {"Ref": "abc"} in the CloudFormation file to "ABC".'
    ),
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "txt"], case_sensitive=False),
    default="txt",
    help="Output format",
    show_default=True,
)
@click.option(
    "--output-folder",
    type=click.Path(exists=True, resolve_path=True, writable=True, file_okay=False),
    help="If not present, result will be sent to stdout",
)
@click.option(
    "--logging",
    "logging_level",
    type=click.Choice(LOGGING_LEVELS.keys(), case_sensitive=True),
    default="INFO",
    help="Logging level",
    show_default=True,
)
def cli(templates, logging_level, resolve_parameters, **kwargs):
    """Analyse AWS Cloudformation templates passed by parameter."""
    try:
        setup_logging(logging_level)

        if kwargs["resolve"] and resolve_parameters:
            resolve_parameters = convert_json_or_yaml_to_dict(resolve_parameters.read())

        for template in templates:
            process_template(template=template, resolve_parameters=resolve_parameters, **kwargs)

    except Exception as e:
        logging.exception(e)
        try:
            sys.exit(e.errno)
        except AttributeError:
            sys.exit(1)


if __name__ == "__main__":
    cli()
