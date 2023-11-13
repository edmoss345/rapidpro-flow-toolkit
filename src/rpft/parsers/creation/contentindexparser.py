import importlib
from collections import OrderedDict

from rpft.parsers.creation.contentindexrowmodel import ContentIndexRowModel
from rpft.parsers.common.cellparser import CellParser
from rpft.parsers.common.sheetparser import SheetParser
from rpft.parsers.common.rowparser import RowParser
from rpft.rapidpro.models.containers import RapidProContainer
from rpft.parsers.creation.flowparser import FlowParser
from rpft.parsers.creation.campaignparser import CampaignParser
from rpft.parsers.creation.campaigneventrowmodel import CampaignEventRowModel
from rpft.parsers.creation.tagmatcher import TagMatcher
from rpft.logger.logger import get_logger, logging_context
from rpft.parsers.sheets import Sheet

LOGGER = get_logger()


class TemplateSheet:
    def __init__(self, table, argument_definitions):
        self.table = table
        self.argument_definitions = argument_definitions


class ParserError(Exception):
    pass


class ContentIndexParser:
    def __init__(
        self,
        sheet_reader=None,
        user_data_model_module_name=None,
        tag_matcher=TagMatcher(),
    ):
        self.reader = sheet_reader
        self.tag_matcher = tag_matcher
        self.template_sheets = {}  # values: tablib tables
        self.data_sheets = {}  # values: OrderedDicts of RowModels
        self.flow_definition_rows = []  # list of ContentIndexRowModel
        self.campaign_parsers = {}  # list of CampaignParser

        if user_data_model_module_name:
            self.user_models_module = importlib.import_module(
                user_data_model_module_name
            )

        indices = self.reader.get_sheets_by_name("content_index")

        if not indices:
            LOGGER.critical("No content index sheet provided")

        for sheet in indices:
            self._process_content_index_table(sheet)

        self._populate_missing_templates()

    def _process_content_index_table(self, sheet: Sheet):
        row_parser = RowParser(ContentIndexRowModel, CellParser())
        sheet_parser = SheetParser(row_parser, sheet.table)
        content_index_rows = sheet_parser.parse_all()
        for row_idx, row in enumerate(content_index_rows, start=2):
            logging_prefix = f"{sheet.reader.name}-{sheet.name} | row {row_idx}"
            with logging_context(logging_prefix):
                if row.status == "draft":
                    continue
                if not self.tag_matcher.matches(row.tags):
                    continue
                if row.type == "content_index":
                    if not len(row.sheet_name) == 1:
                        LOGGER.critical(
                            "For content_index rows, "
                            "exactly one sheet_name has to be specified"
                        )
                    sheet_name = row.sheet_name[0]
                    sheet = self._get_sheet_or_die(sheet_name)
                    with logging_context(f"{sheet.name}"):
                        self._process_content_index_table(sheet)
                elif row.type == "data_sheet":
                    if not len(row.sheet_name) >= 1:
                        LOGGER.critical(
                            "For data_sheet rows, at least one "
                            "sheet_name has to be specified"
                        )
                    self._process_data_sheet(
                        row.sheet_name, row.new_name, row.data_model
                    )
                elif row.type in ["template_definition", "create_flow"]:
                    if not len(row.sheet_name) == 1:
                        LOGGER.critical(
                            "For template_definition/create_flow rows, "
                            "exactly one sheet_name has to be specified"
                        )
                    if row.type == "template_definition":
                        self._add_template(row, True)
                    else:
                        self.flow_definition_rows.append((logging_prefix, row))
                elif row.type == "create_campaign":
                    if not len(row.sheet_name) == 1:
                        LOGGER.critical(
                            "For create_campaign rows, exactly one "
                            "sheet_name has to be specified"
                        )
                    campaign_parser = self.create_campaign_parser(row)
                    name = campaign_parser.campaign.name
                    if name in self.campaign_parsers:
                        LOGGER.warning(
                            f"Duplicate campaign definition sheet '{name}'. "
                            "Overwriting previous definition."
                        )
                    self.campaign_parsers[name] = (logging_prefix, campaign_parser)
                else:
                    LOGGER.error(f"invalid type: '{row.type}'")

    def _add_template(self, row, update_duplicates=False):
        sheet_name = row.sheet_name[0]

        if sheet_name in self.template_sheets and update_duplicates:
            LOGGER.info(
                f"Duplicate template definition sheet '{sheet_name}'. "
                "Overwriting previous definition."
            )
        if sheet_name not in self.template_sheets or update_duplicates:
            sheet = self._get_sheet_or_die(sheet_name)
            self.template_sheets[sheet_name] = TemplateSheet(
                sheet.table, row.template_argument_definitions
            )

    def _populate_missing_templates(self):
        for logging_prefix, row in self.flow_definition_rows:
            with logging_context(f"{logging_prefix} | {row.sheet_name[0]}"):
                self._add_template(row)

    def _get_sheet_or_die(self, sheet_name):
        candidates = self.reader.get_sheets_by_name(sheet_name)

        if not candidates:
            raise ParserError(
                "Sheet not found",
                {"name": sheet_name},
            )

        active = candidates[-1]

        if len(candidates) > 1:
            readers = [c.reader.name for c in candidates]
            LOGGER.warning(
                "Duplicate sheets found, "
                + str(
                    {
                        "name": sheet_name,
                        "readers": readers,
                        "active": active.reader.name,
                    }
                ),
            )

        return active

    def _process_data_sheet(self, sheet_names, new_name, data_model_name):
        if not hasattr(self, "user_models_module"):
            LOGGER.critical(
                "If there are data sheets, a user_data_model_module_name "
                "has to be provided"
            )
            return
        if not data_model_name:
            LOGGER.critical("No data_model_name provided for data sheet.")
            return
        if len(sheet_names) > 1 and not new_name:
            LOGGER.critical(
                "If multiple sheets are concatenated, a new_name has to be provided"
            )
            return
        if not new_name:
            new_name = sheet_names[0]
        if new_name in self.data_sheets:
            LOGGER.warn(
                f"Duplicate data sheet {new_name}. Overwriting previous definition."
            )
        content = OrderedDict()
        for sheet_name in sheet_names:
            with logging_context(sheet_name):
                data_table = self._get_sheet_or_die(sheet_name).table
                try:
                    user_model = getattr(self.user_models_module, data_model_name)
                except AttributeError:
                    LOGGER.critical(
                        f'Undefined data_model_name "{data_model_name}" '
                        f"in {self.user_models_module}."
                    )
                    return
                row_parser = RowParser(user_model, CellParser())
                sheet_parser = SheetParser(row_parser, data_table)
                data_rows = sheet_parser.parse_all()
                sheet_content = OrderedDict((row.ID, row) for row in data_rows)
                content.update(sheet_content)
        self.data_sheets[new_name] = content

    def get_data_model_instance(self, sheet_name, row_id):
        return self.data_sheets[sheet_name][row_id]

    def get_all_data_model_instances(self, sheet_name):
        return self.data_sheets[sheet_name]

    def get_template_sheet(self, name):
        return self.template_sheets[name]

    def get_node_group(
        self, template_name, data_sheet, data_row_id, template_arguments
    ):
        if (data_sheet and data_row_id) or (not data_sheet and not data_row_id):
            with logging_context(f"{template_name}"):
                return self._parse_flow(
                    template_name,
                    data_sheet,
                    data_row_id,
                    template_arguments,
                    RapidProContainer(),
                    parse_as_block=True,
                )
        else:
            LOGGER.critical(
                "For insert_as_block, either both data_sheet and data_row_id "
                "or neither have to be provided."
            )

    def parse_all(self):
        rapidpro_container = RapidProContainer()
        self.parse_all_flows(rapidpro_container)
        self.parse_all_campaigns(rapidpro_container)
        return rapidpro_container

    def create_campaign_parser(self, row):
        sheet_name = row.sheet_name[0]
        sheet = self._get_sheet_or_die(sheet_name)
        row_parser = RowParser(CampaignEventRowModel, CellParser())
        sheet_parser = SheetParser(row_parser, sheet.table)
        rows = sheet_parser.parse_all()
        return CampaignParser(row.new_name or sheet_name, row.group, rows)

    def parse_all_campaigns(self, rapidpro_container):
        for logging_prefix, campaign_parser in self.campaign_parsers.values():
            sheet_name = campaign_parser.campaign.name
            with logging_context(f"{logging_prefix} | {sheet_name}"):
                campaign = campaign_parser.parse()
                rapidpro_container.add_campaign(campaign)

    def parse_all_flows(self, rapidpro_container):
        flows = {}
        for logging_prefix, row in self.flow_definition_rows:
            with logging_context(f"{logging_prefix} | {row.sheet_name[0]}"):
                if row.data_sheet and not row.data_row_id:
                    data_rows = self.get_all_data_model_instances(row.data_sheet)
                    for data_row_id in data_rows.keys():
                        with logging_context(f'with data_row_id "{data_row_id}"'):
                            flow = self._parse_flow(
                                row.sheet_name[0],
                                row.data_sheet,
                                data_row_id,
                                row.template_arguments,
                                rapidpro_container,
                                row.new_name,
                            )
                            if flow.name in flows:
                                LOGGER.warning(
                                    f"Multiple definitions of flow '{flow.name}'. "
                                    "Overwriting."
                                )
                            flows[flow.name] = flow
                elif not row.data_sheet and row.data_row_id:
                    LOGGER.critical(
                        "For create_flow, if data_row_id is provided, "
                        "data_sheet must also be provided."
                    )
                else:
                    flow = self._parse_flow(
                        row.sheet_name[0],
                        row.data_sheet,
                        row.data_row_id,
                        row.template_arguments,
                        rapidpro_container,
                        row.new_name,
                    )
                    if flow.name in flows:
                        LOGGER.warning(
                            f"Multiple definitions of flow '{flow.name}'. "
                            "Overwriting."
                        )
                    flows[flow.name] = flow
        for flow in flows.values():
            rapidpro_container.add_flow(flow)

    def _parse_flow(
        self,
        sheet_name,
        data_sheet,
        data_row_id,
        template_arguments,
        rapidpro_container,
        new_name="",
        parse_as_block=False,
    ):
        base_name = new_name or sheet_name
        if data_sheet and data_row_id:
            flow_name = " - ".join([base_name, data_row_id])
            context = self.get_data_model_instance(data_sheet, data_row_id)
        else:
            if data_sheet or data_row_id:
                LOGGER.warn(
                    "For create_flow, if no data_sheet is provided, "
                    "data_row_id should be blank as well."
                )
            flow_name = base_name
            context = {}
        template_sheet = self.get_template_sheet(sheet_name)
        template_table = template_sheet.table
        template_argument_definitions = template_sheet.argument_definitions
        context = dict(context)
        self.map_template_arguments_to_context(
            template_argument_definitions, template_arguments, context
        )
        flow_parser = FlowParser(
            rapidpro_container,
            flow_name,
            template_table,
            context=context,
            content_index_parser=self,
        )
        if parse_as_block:
            return flow_parser.parse_as_block()
        else:
            return flow_parser.parse(add_to_container=False)

    def map_template_arguments_to_context(self, arg_defs, args, context):
        # Template arguments are positional arguments.
        # This function maps them to the arguments from the template
        # definition, and adds the values of the arguments to the context
        # with the appropriate variable name (from the definition)
        if len(args) > len(arg_defs):
            # Check if these args are non-empty.
            # Once the row parser is cleaned up to eliminate trailing ''
            # entries, this won't be necessary
            extra_args = args[len(arg_defs) :]
            non_empty_extra_args = [ea for ea in extra_args if ea]
            if non_empty_extra_args:
                LOGGER.warn("Too many arguments provided to template")
            # All extra args are blank. Truncate them
            args = args[: len(arg_defs)]
        args_padding = [""] * (len(arg_defs) - len(args))
        for arg_def, arg in zip(arg_defs, args + args_padding):
            if arg_def.name in context:
                LOGGER.critical(
                    f'Template argument "{arg_def.name}" doubly defined '
                    f'in context: "{context}"'
                )
            arg_value = arg if arg != "" else arg_def.default_value
            if arg_value == "":
                LOGGER.critical(
                    f'Required template argument "{arg_def.name}" not provided'
                )
            if arg_def.type == "sheet":
                context[arg_def.name] = self.data_sheets[arg_value]
            else:
                context[arg_def.name] = arg_value
