import base64
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api import reader


class ReaderTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"ALLOWED_REPOSITORY":"Bhanuch2006/deployiq", "ALLOWED_REPOSITORY_ID":"1421278672"})
        env.start(); self.addCleanup(env.stop)
        self.event={"routeKey":"GET /runs", "requestContext":{"authorizer":{"jwt":{"claims":{"sub":"team-user", "token_use":"id"}}}}}

    def test_unauthenticated_calls_never_reach_database(self):
        with patch.object(reader, 'table') as table:
            result=reader.handler({"routeKey":"GET /runs"},None)
            self.assertEqual(result['statusCode'],401)
            table.assert_not_called()

    def test_access_token_is_rejected_by_reader(self):
        self.event['requestContext']['authorizer']['jwt']['claims']['token_use']='access'
        self.assertEqual(reader.handler(self.event,None)['statusCode'],401)

    def test_query_is_scoped_and_summary_excludes_logs(self):
        with patch.object(reader,'table') as table:
            table.return_value.query.return_value={'Items':[{'run_key':'repo#1#1','run_id':Decimal(1),'sanitized_log_excerpt':'private details','analysis_source':'rules'}]}
            result=reader.handler(self.event,None)
            options=table.return_value.query.call_args.kwargs
        body=json.loads(result['body'])
        self.assertEqual(options['ExpressionAttributeValues'],{':repo':'Bhanuch2006/deployiq'})
        self.assertFalse(options['ScanIndexForward'])
        self.assertNotIn('sanitized_log_excerpt',body['runs'][0])
        self.assertEqual(body['runs'][0]['run_id'],1)
        self.assertEqual(result['headers']['cache-control'],'no-store')

    def test_cross_repository_cursor_is_rejected(self):
        cursor=reader.encode_cursor({'repository':'other/repo','run_key':'other/repo#1#1','received_at':'2026-10-16'})
        self.event['queryStringParameters']={'cursor':cursor}
        with patch.object(reader,'table') as table:
            self.assertEqual(reader.handler(self.event,None)['statusCode'],400)
            table.assert_not_called()

    def test_invalid_cursor_is_rejected(self):
        self.event['queryStringParameters']={'cursor':'not-json'}
        self.assertEqual(reader.handler(self.event,None)['statusCode'],400)

    def test_cursor_round_trip(self):
        key={'repository':'Bhanuch2006/deployiq','run_key':'Bhanuch2006/deployiq#1#1','received_at':'2026-10-16T10:00:00+00:00'}
        with patch.object(reader,'table') as table:
            table.return_value.query.return_value={'Items':[],'LastEvaluatedKey':key}
            result=reader.handler(self.event,None)
        cursor=json.loads(result['body'])['next_cursor']
        self.assertEqual(reader.decode_cursor(cursor,'Bhanuch2006/deployiq'),key)

    def test_limit_is_bounded(self):
        for value in ['0','51','nope']:
            with self.subTest(value=value):
                self.event['queryStringParameters']={'limit':value}
                self.assertEqual(reader.handler(self.event,None)['statusCode'],400)

    def detail_event(self):
        return self.event|{'routeKey':'GET /runs/{runId}/attempts/{attempt}','pathParameters':{'runId':'123','attempt':'2'}}

    def test_detail_key_is_derived_from_registered_repository(self):
        with patch.object(reader,'table') as table:
            table.return_value.get_item.return_value={'Item':{'repository':'Bhanuch2006/deployiq','repository_id':1421278672,'run_id':123,'run_attempt':2,'diagnosis':{'root_cause':'missing dependency'},'private_field':'never expose'}}
            result=reader.handler(self.detail_event(),None)
        self.assertEqual(table.return_value.get_item.call_args.kwargs['Key'],{'run_key':'Bhanuch2006/deployiq#123#2'})
        run=json.loads(result['body'])['run']
        self.assertIn('diagnosis',run)
        self.assertNotIn('private_field',run)

    def test_wrong_repository_id_is_not_returned(self):
        with patch.object(reader,'table') as table:
            table.return_value.get_item.return_value={'Item':{'repository':'Bhanuch2006/deployiq','repository_id':999}}
            self.assertEqual(reader.handler(self.detail_event(),None)['statusCode'],404)

    def test_missing_run_is_not_found(self):
        with patch.object(reader,'table') as table:
            table.return_value.get_item.return_value={}
            self.assertEqual(reader.handler(self.detail_event(),None)['statusCode'],404)

    def test_invalid_run_id_does_not_reach_database(self):
        event=self.detail_event();event['pathParameters']['runId']='../other'
        with patch.object(reader,'table') as table:
            self.assertEqual(reader.handler(event,None)['statusCode'],400)
            table.assert_not_called()

    def test_database_errors_do_not_expose_exception(self):
        with patch.object(reader,'table') as table, self.assertLogs(reader.logger,level='ERROR'):
            table.return_value.query.side_effect=RuntimeError('sensitive database error')
            result=reader.handler(self.event,None)
        self.assertEqual(result['statusCode'],503)
        self.assertNotIn('sensitive',result['body'])
