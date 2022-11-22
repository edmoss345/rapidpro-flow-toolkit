import json
import unittest
import tablib

from parsers.creation.flowparser import FlowParser
from tests.utils import get_dict_from_csv, get_table_from_file, find_destination_uuid, Context, find_node_by_uuid, traverse_flow
from rapidpro.models.containers import RapidProContainer, FlowContainer
from rapidpro.models.actions import Group, AddContactGroupAction
from rapidpro.models.nodes import BasicNode

from parsers.common.rowparser import RowParser
from parsers.creation.flowrowmodel import FlowRowModel
from parsers.common.cellparser import CellParser
from parsers.common.tests.mock_sheetparser import MockSheetParser

from .row_data import get_start_row, get_unconditional_node_from_1, get_conditional_node_from_1

class TestParsing(unittest.TestCase):

    def setUp(self) -> None:
        self.row_parser = RowParser(FlowRowModel, CellParser())

    def get_render_output_from_file(self, flow_name, filename):
        dict_rows = get_dict_from_csv(filename)
        self.rows = [self.row_parser.parse_row(row) for row in dict_rows]
        return self.get_render_output(flow_name, self.rows)

    def get_render_output(self, flow_name, input_rows):
        sheet_parser = MockSheetParser(None, input_rows)
        parser = FlowParser(RapidProContainer(), flow_name=flow_name, sheet_parser=sheet_parser)
        flow_container = parser.parse()
        return flow_container.render()

    def test_send_message(self):
        render_output = self.get_render_output('send_message', [get_start_row()])

        node_0 = render_output['nodes'][0]
        node_0_actions = node_0['actions']

        self.assertEqual(node_0_actions[0]['type'], 'send_msg')
        self.assertEqual(node_0_actions[0]['text'], 'Text of message')
        self.assertEqual(len(node_0_actions[0]['attachments']), 0)
        self.assertEqual(node_0_actions[0]['quick_replies'], ['Answer 1', 'Answer 2'])

    def test_linear(self):
        data_row1 = get_start_row()
        data_row2 = get_unconditional_node_from_1()
        data_row2.edges[0].from_ = ''  # implicit continue from last node
        render_output = self.get_render_output('linear', [data_row1, data_row2])

        node_0 = render_output['nodes'][0]
        node_1 = render_output['nodes'][1]
        node_1_actions = node_1['actions']

        self.assertEqual(node_1_actions[0]['text'], 'Unconditional message')
        self.assertEqual(len(node_0['exits']), 1)
        self.assertIsNone(node_0.get('router'))
        self.assertEqual(node_0['exits'][0]['destination_uuid'], node_1['uuid'])
        self.assertEqual(node_1['exits'][0]['destination_uuid'], None)

    def test_only_conditional(self):
        data_row1 = get_start_row()
        data_row3 = get_conditional_node_from_1()
        render_output = self.get_render_output('only_conditional', [data_row1, data_row3])

        self.assertEqual(len(render_output['nodes']), 3)
        node_0 = render_output['nodes'][0]
        node_1 = render_output['nodes'][1]
        node_2 = render_output['nodes'][2]
        node_2_actions = node_2['actions']

        self.assertEqual(node_2_actions[0]['text'], 'Message if @fields.name == 3')
        self.assertEqual(len(node_1['exits']), 2)
        self.assertIsNone(node_0.get('router'))
        self.assertIsNotNone(node_1.get('router'))
        self.assertEqual(node_0['exits'][0]['destination_uuid'], node_1['uuid'])
        self.assertEqual(node_1['exits'][0]['destination_uuid'], node_2['uuid'])
        self.assertEqual(node_1['exits'][1]['destination_uuid'], None)
        self.assertEqual(node_2['exits'][0]['destination_uuid'], None)

    def test_split1(self):
        data_row1 = get_start_row()
        data_row2 = get_unconditional_node_from_1()
        data_row3 = get_conditional_node_from_1()
        data_rows = [data_row1, data_row2, data_row3]
        self.check_split(data_rows)

    def test_split2(self):
        data_row1 = get_start_row()
        data_row2 = get_unconditional_node_from_1()
        data_row3 = get_conditional_node_from_1()
        data_rows = [data_row1, data_row3, data_row2]
        self.check_split(data_rows)

    def check_split(self, data_rows):
        render_output = self.get_render_output('split', data_rows)

        node_start = render_output['nodes'][0]
        node_switch = find_node_by_uuid(render_output, node_start['exits'][0]['destination_uuid'])
        default_destination = find_destination_uuid(node_switch, Context(variables={'@fields.name':'5'}))
        node_2 = find_node_by_uuid(render_output, default_destination)
        cond_destination = find_destination_uuid(node_switch, Context(variables={'@fields.name':'3'}))
        node_3 = find_node_by_uuid(render_output, cond_destination)
        node_2_actions = node_2['actions']
        node_3_actions = node_3['actions']

        self.assertEqual(node_3_actions[0]['text'], 'Message if @fields.name == 3')
        self.assertEqual(node_2_actions[0]['text'], 'Unconditional message')
        self.assertEqual(len(node_switch['exits']), 2)
        self.assertIsNone(node_start.get('router'))
        self.assertIsNotNone(node_switch.get('router'))

    def test_no_switch_node_rows(self):
        render_output = self.get_render_output_from_file('no_switch_node', 'input/no_switch_nodes.csv')

        # Check that node UUIDs are maintained
        nodes = render_output['nodes']
        actual_node_uuids = [node['uuid'] for node in nodes]
        expected_node_uuids = [row.node_uuid for row in self.rows][3:]  # The first 4 rows are actions joined into a single node.
        self.assertEqual(expected_node_uuids, actual_node_uuids)

        self.assertEqual(render_output['name'], 'no_switch_node')
        self.assertEqual(render_output['type'], 'messaging')
        self.assertEqual(render_output['language'], 'eng')

        self.assertEqual(len(render_output['nodes']), 5)

        node_0 = render_output['nodes'][0]
        node_0_actions = node_0['actions']

        self.assertEqual(len(node_0_actions), 4)

        self.assertEqual(node_0_actions[0]['type'], 'send_msg')
        self.assertEqual(node_0_actions[0]['text'], 'this is a send message node')
        self.assertEqual(len(node_0_actions[0]['attachments']), 0)
        self.assertIn('qr1', node_0_actions[0]['quick_replies'])
        self.assertIn('qr2', node_0_actions[0]['quick_replies'])

        self.assertEqual(node_0_actions[1]['type'], 'send_msg')
        self.assertEqual(node_0_actions[1]['text'], 'message with image')
        self.assertEqual(len(node_0_actions[1]['attachments']), 1)
        self.assertEqual(node_0_actions[1]['attachments'][0], 'image u')
        self.assertEqual(len(node_0_actions[1]['quick_replies']), 0)

        self.assertEqual(node_0_actions[2]['type'], 'send_msg')
        self.assertEqual(node_0_actions[2]['text'], 'message with audio')
        self.assertEqual(len(node_0_actions[2]['attachments']), 1)
        self.assertEqual(node_0_actions[2]['attachments'][0], 'audio u')
        self.assertEqual(len(node_0_actions[2]['quick_replies']), 0)

        self.assertEqual(node_0_actions[3]['type'], 'send_msg')
        self.assertEqual(node_0_actions[3]['text'], 'message with video')
        self.assertEqual(len(node_0_actions[3]['attachments']), 1)
        self.assertEqual(node_0_actions[3]['attachments'][0], 'video u')
        self.assertEqual(len(node_0_actions[3]['quick_replies']), 0)

        node_1 = render_output['nodes'][1]
        node_1_actions = node_1['actions']

        self.assertEqual(node_0['exits'][0]['destination_uuid'], node_1['uuid'])

        self.assertEqual(len(node_1_actions), 1)
        self.assertEqual(node_1_actions[0]['type'], 'set_contact_field')
        self.assertEqual(node_1_actions[0]['field']['key'], 'test_variable')
        self.assertEqual(node_1_actions[0]['field']['name'], 'test variable')
        self.assertEqual(node_1_actions[0]['value'], 'test value ')

        node_2 = render_output['nodes'][2]
        node_2_actions = render_output['nodes'][2]['actions']

        self.assertEqual(node_1['exits'][0]['destination_uuid'], node_2['uuid'])

        self.assertEqual(len(node_2_actions), 1)
        self.assertEqual(node_2_actions[0]['type'], 'add_contact_groups')
        self.assertEqual(len(node_2_actions[0]['groups']), 1)
        self.assertEqual(node_2_actions[0]['groups'][0]['name'], 'test group')

        node_3 = render_output['nodes'][3]
        node_3_actions = render_output['nodes'][3]['actions']

        self.assertEqual(node_2['exits'][0]['destination_uuid'], node_3['uuid'])
        self.assertEqual(len(node_3_actions), 1)
        self.assertEqual('remove_contact_groups', node_3_actions[0]['type'])
        self.assertEqual(len(node_3_actions[0]['groups']), 1)
        self.assertEqual('test group', node_3_actions[0]['groups'][0]['name'])

        # Make sure it's the same group
        self.assertEqual(node_2_actions[0]['groups'][0]['uuid'], node_3_actions[0]['groups'][0]['uuid'])

        node_4 = render_output['nodes'][4]
        node_4_actions = render_output['nodes'][4]['actions']

        self.assertEqual(node_3['exits'][0]['destination_uuid'], node_4['uuid'])
        self.assertEqual(len(node_4_actions), 1)
        self.assertEqual('set_run_result', node_4_actions[0]['type'])
        self.assertEqual('result name', node_4_actions[0]['name'])
        self.assertEqual('result value', node_4_actions[0]['value'])

        self.assertIsNone(node_4['exits'][0]['destination_uuid'])

        # Check UI positions/types of the first two nodes
        render_ui = render_output['_ui']['nodes']
        self.assertIn(node_0['uuid'], render_ui)
        pos0 = render_ui[node_0['uuid']]['position']
        self.assertEqual((280, 73), (pos0['left'], pos0['top']))
        self.assertEqual('execute_actions', render_ui[node_0['uuid']]['type'])
        self.assertIn(node_1['uuid'], render_ui)
        pos1 = render_ui[node_1['uuid']]['position']
        self.assertEqual((280, 600), (pos1['left'], pos1['top']))
        self.assertEqual('execute_actions', render_ui[node_1['uuid']]['type'])

    def test_switch_node_rows(self):
        render_output = self.get_render_output_from_file('switch_node', 'input/switch_nodes.csv')

        # Check that node UUIDs are maintained
        nodes = render_output['nodes']
        actual_node_uuids = [node['uuid'] for node in nodes]
        expected_node_uuids = [row.node_uuid for row in self.rows]
        self.assertEqual(expected_node_uuids, actual_node_uuids)

        # Check that No Response category is created even if not connected
        last_wait_node = nodes[-2]
        self.assertEqual('No Response', last_wait_node['router']['categories'][-1]['name'])

        # TODO: Ideally, there should be more explicit tests here.
        # At least the functionality is covered by the integration tests simulating the flow.
        # print(json.dumps(render_output, indent=2))

        render_ui = render_output['_ui']['nodes']
        f_uuid = lambda i: render_output['nodes'][i]['uuid']
        f_uipos_dict = lambda i: render_ui[f_uuid(i)]['position']
        f_uipos = lambda i: (f_uipos_dict(i)['left'], f_uipos_dict(i)['top'])
        f_uitype = lambda i: render_ui[f_uuid(i)]['type']
        self.assertIn(f_uuid(0), render_ui)
        self.assertEqual((340, 0), f_uipos(0))
        self.assertEqual((360, 180), f_uipos(1))
        self.assertEqual((840, 1200), f_uipos(-2))
        self.assertEqual((740, 300), f_uipos(-1))
        self.assertEqual("wait_for_response", f_uitype(0))
        self.assertEqual("split_by_subflow", f_uitype(1))
        self.assertEqual("split_by_expression", f_uitype(2))
        self.assertEqual("split_by_contact_field", f_uitype(3))
        self.assertEqual("split_by_run_result", f_uitype(4))
        self.assertEqual("split_by_groups", f_uitype(5))
        self.assertEqual("wait_for_response", f_uitype(6))
        self.assertEqual("split_by_random", f_uitype(7))
        self.assertEqual("execute_actions", f_uitype(8))
        self.assertEqual("execute_actions", f_uitype(9))
        self.assertEqual("wait_for_response", f_uitype(-2))

        # Ensure that wait_for_response cases are working as intended
        node6 = render_output['nodes'][6]
        categories = node6["router"]["categories"]
        self.assertEqual(len(categories), 3)
        self.assertEqual(categories[0]["name"], 'A')
        self.assertEqual(categories[1]["name"], 'Other')
        self.assertEqual(categories[2]["name"], 'No Response')
        self.assertEqual(len(node6["router"]["cases"]), 1)

    def test_groups_and_flows(self):
        # We check that references flows and group are assigned uuids consistently
        tiny_uuid = '00000000-acec-434f-bc7c-14c584fc4bc8'
        test_uuid = '8224bfe2-acec-434f-bc7c-14c584fc4bc8'
        other_uuid = '12345678-acec-434f-bc7c-14c584fc4bc8'
        test_group_dict = {'name': 'test group', 'uuid' : test_uuid}
        other_group_dict = {'name': 'other group', 'uuid' : other_uuid}
        tiny_flow_dict = {'name': 'tiny_flow', 'uuid' : tiny_uuid}

        # Make a flow with a single group node (no UUIDs), and put it into new container
        node = BasicNode()
        node.add_action(AddContactGroupAction([Group('test group'), Group('other group')]))
        tiny_flow = FlowContainer('tiny_flow', uuid=tiny_uuid)
        tiny_flow.add_node(node)
        container = RapidProContainer(groups=[Group('other group', other_uuid)])
        container.add_flow(tiny_flow)

        # Add flow from sheet into container
        dict_rows = get_dict_from_csv('input/groups_and_flows.csv')
        rows = [self.row_parser.parse_row(row) for row in dict_rows]
        sheet_parser = MockSheetParser(None, rows)
        parser = FlowParser(container, flow_name='groups_and_flows', sheet_parser=sheet_parser)
        parser.parse()
        # Render also invokes filling in all the flow/group UUIDs
        render_output = container.render()

        # Ensure container groups are complete and have correct UUIDs
        self.assertIn(test_group_dict, render_output['groups'])
        self.assertIn(other_group_dict, render_output['groups'])
        # These UUIDs are inferred from the sheet/the container groups, respectively
        self.assertEqual(render_output['flows'][0]['nodes'][0]['actions'][0]['groups'], [test_group_dict, other_group_dict])

        nodes = render_output['flows'][1]['nodes']
        # This UUID appears only in a later occurrence of the group in the sheet
        self.assertEqual(nodes[0]['actions'][0]['groups'], [test_group_dict])
        # This UUID is missing from the sheet, but explicit in the flow definition
        self.assertEqual(nodes[1]['actions'][0]['flow'], tiny_flow_dict)
        # This UUID is explicit in the sheet
        self.assertEqual(nodes[2]['actions'][0]['groups'], [test_group_dict])
        # This UUID appears in a previous occurrence of the group in the sheet
        self.assertEqual(nodes[3]['router']['cases'][0]['arguments'], [test_uuid, 'test group'])
        # This UUID was part of the groups in the container, but not in the sheet
        self.assertEqual(nodes[6]['actions'][0]['groups'], [other_group_dict])

        tiny_flow.uuid = 'something else'
        with self.assertRaises(ValueError):
            # The enter_flow node has a different uuid than the flow
            container.validate()

        tiny_flow.uuid = tiny_uuid
        container.flows[1].nodes[2].actions[0].groups[0].uuid = 'something else'
        with self.assertRaises(ValueError):
            # The group is referenced by 2 different UUIDs
            container.validate()


class TestLoops(unittest.TestCase):

    def setUp(self) -> None:
        self.row_parser = RowParser(FlowRowModel, CellParser())

    def render_output_from_table_data(self, table_data):
        table = tablib.import_set(table_data, format='csv')
        parser = FlowParser(RapidProContainer(), 'basic loop', table)
        return parser.parse().render()

    def run_example(self, table_data, messages_exp, context=None):
        render_output = self.render_output_from_table_data(table_data)
        actions = traverse_flow(render_output, context or Context())
        actions_exp = list(zip(['send_msg']*len(messages_exp), messages_exp))
        self.assertEqual(actions, actions_exp)

    def test_basic_loop(self):
        table_data = (
            'row_id,type,from,loop_variable,message_text\n'
            '1,begin_for,start,i,1;2;3\n'
            ',send_message,,,{{i}}. Some text\n'
            ',end_for,,,\n'
        )
        render_output = self.render_output_from_table_data(table_data)
        nodes = render_output["nodes"]
        self.assertEqual(len(nodes), 3)
        self.assertEqual(nodes[0]["actions"][0]["type"], 'send_msg')
        self.assertEqual(nodes[0]["actions"][0]["text"], '1. Some text')
        self.assertEqual(nodes[1]["actions"][0]["text"], '2. Some text')
        self.assertEqual(nodes[2]["actions"][0]["text"], '3. Some text')
        # Also check that the connectivity is correct
        messages_exp = ['1. Some text','2. Some text','3. Some text']
        self.run_example(table_data, messages_exp)

    def test_one_element_loop(self):
        table_data = (
            'row_id,type,from,loop_variable,message_text\n'
            '1,begin_for,start,i,1\n'
            ',send_message,,,{{i}}. Some text\n'
            ',end_for,,,\n'
        )
        render_output = self.render_output_from_table_data(table_data)
        nodes = render_output["nodes"]
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["actions"][0]["type"], 'send_msg')
        self.assertEqual(nodes[0]["actions"][0]["text"], '1. Some text')

    def test_nested_loop(self):
        table_data = (
            'row_id,type,from,loop_variable,message_text\n'
            '1,begin_for,start,i,1;2\n'
            ',begin_for,,j,A;B\n'
            ',send_message,,,{{i}}{{j}}. Some text\n'
            ',end_for,,,\n'
            ',end_for,,,\n'
        )
        messages_exp = ['1A. Some text','1B. Some text','2A. Some text','2B. Some text']
        self.run_example(table_data, messages_exp)

    def test_loop_within_other_nodes(self):
        table_data = (
            'row_id,type,from,loop_variable,message_text\n'
            ',send_message,start,,Starting text\n'
            '2,begin_for,,i,1;2\n'
            ',send_message,,,{{i}}. Some text\n'
            ',end_for,,,\n'
            ',send_message,,,Following text\n'
        )
        messages_exp = ['Starting text','1. Some text','2. Some text','Following text']
        self.run_example(table_data, messages_exp)

    def test_nested_loop_with_other_nodes(self):
        table_data = (
            'row_id,type,from,loop_variable,message_text\n'
            '1,begin_for,start,i,1;2\n'
            ',begin_for,,j,A;B\n'
            ',send_message,,,{{i}}{{j}}. Some text\n'
            ',end_for,,,\n'
            ',send_message,,,End of inner loop\n'
            ',end_for,,,\n'
            ',send_message,,,End of outer loop\n'
        )
        messages_exp = ['1A. Some text','1B. Some text','End of inner loop',
                        '2A. Some text','2B. Some text','End of inner loop','End of outer loop']
        self.run_example(table_data, messages_exp)

    def test_loop_with_explicit_following_node(self):
        table_data = (
            'row_id,type,from,loop_variable,message_text\n'
            '2,begin_for,,i,1;2\n'
            ',send_message,,,{{i}}. Some text\n'
            ',end_for,,,\n'
            ',send_message,2,,Following text\n'
        )
        messages_exp = ['1. Some text','2. Some text','Following text']
        self.run_example(table_data, messages_exp)

    def test_loop_with_goto(self):
        table_data = (
            'row_id,type,from,condition,loop_variable,message_text\n'
            '2,begin_for,start,,i,1;2\n'
            ',send_message,,,,{{i}}. Some text\n'
            ',end_for,,,,\n'
            '3,wait_for_response,2,,,\n'
            ',go_to,3,hello,,2\n'
            ',send_message,3,,,Following text\n'
        )
        messages_exp = ['1. Some text','2. Some text','Following text']
        self.run_example(table_data, messages_exp, Context(inputs=['goodbye']))
        messages_exp = ['1. Some text','2. Some text','1. Some text','2. Some text','Following text']
        self.run_example(table_data, messages_exp, Context(inputs=['hello', 'goodbye']))

    def test_loop_with_goto_into_middle_of_loop(self):
        table_data = (
            'row_id,type,from,condition,loop_variable,message_text\n'
            '2,begin_for,start,,i,1;2\n'
            'item{{i}},send_message,,,,{{i}}. Some text\n'
            ',end_for,,,,\n'
            '3,wait_for_response,2,,,\n'
            ',go_to,3,hello,,item2\n'
            ',send_message,3,,,Following text\n'
        )
        messages_exp = ['1. Some text','2. Some text','Following text']
        self.run_example(table_data, messages_exp, Context(inputs=['goodbye']))
        messages_exp = ['1. Some text','2. Some text','2. Some text','Following text']
        self.run_example(table_data, messages_exp, Context(inputs=['hello', 'goodbye']))
