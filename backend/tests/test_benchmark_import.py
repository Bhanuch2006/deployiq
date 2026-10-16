import copy
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analysis import worker

class BenchmarkImportTests(unittest.TestCase):
    def setUp(self):
        self.item={'run_key':'Bhanuch2006/deployiq#123#1','repository':'Bhanuch2006/deployiq','repository_id':1421278672,'run_id':123,'run_attempt':1,'head_sha':'abc','name':'DeployIQ Cache Benchmark','conclusion':'success'}
        self.samples=[{'variant':variant,'round':i,'install_seconds':Decimal('5.0') if variant=='baseline' else Decimal('10.0') if i==1 else Decimal('2.0'),'cache_state':'disabled' if variant=='baseline' else 'cold' if i==1 else 'warm'} for i in range(1,5) for variant in ['baseline','cached']]
        self.report={'schema_version':1,'metric':'pip_install_seconds','repository':self.item['repository'],'run_id':'123','run_attempt':'1','head_sha':'abc','samples':self.samples,'summary':{'improvement_percent':999},'python':'3.12','platform':'Linux','requirements_sha256':'abc123','measured_at':'2026-10-16','scope':'Dependency install only'}

    def test_summary_is_recomputed_not_trusted(self):
        result=worker.validate_benchmark(self.report,self.item)
        self.assertEqual(result['summary']['improvement_percent'],60)
        self.assertEqual(result['summary']['cold_seconds'],10)
        self.assertIsInstance(result['summary']['baseline_median_seconds'],Decimal)

    def test_mismatched_commit_is_rejected(self):
        self.report['head_sha']='other'
        with self.assertRaisesRegex(worker.SafeFailure,'identity_mismatch'): worker.validate_benchmark(self.report,self.item)

    def test_duplicate_measurements_are_rejected(self):
        self.report['samples'][0]=self.report['samples'][1]
        with self.assertRaises(worker.SafeFailure): worker.validate_benchmark(self.report,self.item)

    def test_non_finite_or_negative_duration_is_rejected(self):
        for value in [Decimal('NaN'),Decimal('Infinity'),-1,True]:
            with self.subTest(value=value):
                report=copy.deepcopy(self.report);report['samples'][0]['install_seconds']=value
                with self.assertRaises(worker.SafeFailure): worker.validate_benchmark(report,self.item)

    def test_wrong_cache_label_is_rejected(self):
        self.report['samples'][1]['cache_state']='warm'
        with self.assertRaises(worker.SafeFailure): worker.validate_benchmark(self.report,self.item)

    def test_archive_is_imported_without_ai_call(self):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:
            z.writestr('cache-benchmark.json',json.dumps(self.report,default=float))
        table=MagicMock();secrets=MagicMock();secrets.get_secret_value.return_value={'SecretString':'private-token'}
        with patch.dict(os.environ,{'GITHUB_TOKEN_SECRET_ARN':'test-secret'}), patch.object(worker,'github_json',return_value={'artifacts':[{'id':42,'name':'cache-benchmark-123-1','expired':False,'workflow_run':{'head_sha':'abc'}}]}), patch.object(worker,'artifact_archive',return_value=data.getvalue()):
            worker.import_benchmark(self.item,table,secrets)
        values=table.update_item.call_args.kwargs['ExpressionAttributeValues']
        self.assertEqual(values[':status'],'completed')
        self.assertEqual(values[':report']['summary']['improvement_percent'],60)

    def test_completed_import_is_not_repeated(self):
        self.item['benchmark_status']='completed';table=MagicMock();secrets=MagicMock()
        worker.import_benchmark(self.item,table,secrets)
        table.update_item.assert_not_called();secrets.get_secret_value.assert_not_called()
