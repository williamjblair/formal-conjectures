import copy
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch
from conjectures import evaluation, eval_verifier, core


class EvaluationTests(unittest.TestCase):
    def suite(self):
        return {'schema_version':evaluation.SCHEMA,'source':{'repository':'fixture/fc','commit':'a'*40},
                'execution':{'solver_image':'example/solver@sha256:'+'b'*64,'verifier_image':'example/verifier@sha256:'+'c'*64,
                             'toolkit_commit':'d'*40,'agent_seconds':600},
                'cases':[{'id':'plain','declaration':'Fixture.plain','exposure':'Development fixture'}]}

    def test_frozen_suite_rejects_floating_pins_duplicate_tasks_and_missing_exposure(self):
        suite=self.suite();evaluation.validate_suite(suite)
        mutations=[lambda x:x['execution'].update(solver_image='image:latest'),
                   lambda x:x['cases'].append(x['cases'][0]),lambda x:x['cases'][0].pop('exposure'),
                   lambda x:x['source'].update(commit='main')]
        for mutate in mutations:
            value=copy.deepcopy(suite);mutate(value)
            with self.assertRaises(ValueError):evaluation.validate_suite(value)

    def test_harbor_task_has_separate_verifier_and_only_submission_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'environment').mkdir()
            target={'id':'plain','source':{'declaration':'Fixture.plain'},'suite_sha256':'a'*64,'exposure':'known'}
            evaluation.write_task(root,target,self.suite()['execution'])
            config=tomllib.loads((root/'task.toml').read_text())
            self.assertEqual(config['verifier']['environment_mode'],'separate')
            self.assertEqual(config['artifacts'],['/app/Submission.lean','/app/Submission'])
            self.assertFalse((root/'solution').exists())
            self.assertIn('PYTHONPATH=/opt/fc/toolkit',(root/'tests/test.sh').read_text())

    def test_infrastructure_failure_never_emits_zero_reward(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target=root/'target.json'
            core.save(target,{'schema_version':'fc.proof-task.v1','id':'case','suite_sha256':'a'*64})
            with patch.object(eval_verifier,'restrict',side_effect=core.Failure('unqualified_executor','missing sandbox',3)):
                result=eval_verifier.run(target,root,root/'result')
            self.assertEqual(result['status'],'error')
            self.assertFalse((root/'result/reward.txt').exists())
            self.assertEqual(evaluation.summarize(root)['counts']['error'],1)
            with self.assertRaises(core.Failure):eval_verifier.run(target,root,root/'result')
