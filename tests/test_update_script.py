"""Deployment orchestration tests with fake Git/Docker; never touch real containers."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

class UpdateScriptTests(unittest.TestCase):
    def run_script(self, failure='', conventional=False):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'deploy').mkdir();(root/'bin').mkdir()
            shutil.copyfile(Path(__file__).parents[1]/'deploy/update.sh',root/'deploy/update.sh')
            (root/('.env' if conventional else '.env.observatory')).write_text('OBS_LIVE=1\nOBS_RPC_URL=https://rpc.example.com/test\n')
            fake='''#!/usr/bin/env python3
import os,sys,pathlib
args=sys.argv[1:]; name=pathlib.Path(sys.argv[0]).name
with open(os.environ['TEST_LOG'],'a') as f: f.write(name+' '+(' '.join(args[:4]))+'\\n')
fail=os.environ['TEST_FAIL']
if name=='git':
 if args[:2]==['rev-parse','--show-toplevel']: print(os.environ['TEST_ROOT'])
 elif args[:2]==['branch','--show-current']: print('codex/wallet-observatory')
 elif args[:3]==['remote','get-url','origin']: print('https://github.com/rippin/wallet-discovery.git')
 elif args[0]=='status' and fail=='dirty': print(' M user-file')
 elif args[0]=='rev-parse': print('abcdef')
 elif args[0]=='merge-base' and fail=='diverged': sys.exit(1)
else:
 if args[:2]==['compose','build'] and fail=='build': sys.exit(1)
 if args[:2]==['compose','ps']: print('existing-container')
 if args[:2]==['compose','cp']:
  if fail=='backup': sys.exit(1)
  pathlib.Path(args[-1]).touch()
'''
            for command in ('git','docker'):
                p=root/'bin'/command;p.write_text(fake);p.chmod(0o755)
            env={**os.environ,'PATH':str(root/'bin')+os.pathsep+os.environ['PATH'],
                 'TEST_LOG':str(root/'calls'),'TEST_ROOT':str(root),'TEST_FAIL':failure}
            result=subprocess.run(['bash',str(root/'deploy/update.sh')],env=env,capture_output=True,text=True)
            calls=(root/'calls').read_text()
            if conventional:
                self.assertEqual((root/'.env.observatory').read_text(),(root/'.env').read_text())
                self.assertEqual((root/'.env.observatory').stat().st_mode & 0o777,0o600)
            return result,calls
    def test_success_pulls_backs_up_and_starts(self):
        r,c=self.run_script();self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(c.count('git fetch'),1)
        self.assertLess(c.index('docker compose cp'),c.index('docker compose up'))
        self.assertIn('Updated successfully',r.stdout)
    def test_conventional_env_reused_without_prompt(self):
        r,c=self.run_script(conventional=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('Imported existing .env',r.stdout)
        self.assertNotIn('First-time setup',r.stdout)

    def test_local_changes_stop_before_fetch(self):
        r,c=self.run_script('dirty');self.assertNotEqual(r.returncode,0);self.assertNotIn('git fetch',c)
    def test_divergence_stops_before_build(self):
        r,c=self.run_script('diverged');self.assertNotEqual(r.returncode,0);self.assertNotIn('docker compose build',c)
    def test_build_failure_keeps_existing_service(self):
        r,c=self.run_script('build');self.assertNotEqual(r.returncode,0);self.assertNotIn('docker compose up',c)
    def test_backup_failure_blocks_replacement(self):
        r,c=self.run_script('backup');self.assertNotEqual(r.returncode,0);self.assertNotIn('docker compose up',c)

class SetupPromptTests(unittest.TestCase):
    def setup_env(self, credential, password="example-password-1234567890"):
        script=(Path(__file__).parents[1]/'deploy/update.sh').read_text()
        block=script[script.index('    local credential'):script.index('  chmod 600 .env.observatory')]
        block=block.rsplit('  fi',1)[0]
        with tempfile.TemporaryDirectory() as folder:
            result=subprocess.run(['bash','-c','setup() {\n'+block+'\n}\nsetup'],
                cwd=folder,input=credential+'\n'+password+'\n',capture_output=True,text=True)
            path=Path(folder)/'.env.observatory'
            return result,path.read_text() if path.exists() else ''
    def test_chainstack_url_sets_budget_and_no_helius_key(self):
        url='https://solana-mainnet.core.chainstack.com/example'
        r,data=self.setup_env(url)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('OBS_RPC_URL='+url,data)
        self.assertIn('HELIUS_API_KEY=\n',data)
        self.assertIn('OBS_MONTHLY_CREDITS=2700000',data)
        self.assertIn('OBS_RPC_CREDIT_COST=2',data)
        self.assertNotIn(url,r.stdout+r.stderr)
    def test_helius_key_still_supported(self):
        r,data=self.setup_env('example-key')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('HELIUS_API_KEY=example-key',data)
        self.assertIn('OBS_RPC_URL=\n',data)
    def test_url_query_preserved(self):
        url='https://rpc.example.com/v1?api-key=example&mode=full'
        r,data=self.setup_env(url)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('OBS_RPC_URL='+url,data)
    def test_dotenv_interpolation_rejected(self):
        r,data=self.setup_env('https://rpc.example.com/$SECRET')
        self.assertNotEqual(r.returncode,0)
        self.assertEqual(data,'')

    def test_seven_character_password_accepted(self):
        r,data=self.setup_env('example-key','seven77')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('OBS_PASSWORD=seven77',data)
    def test_six_character_password_rejected(self):
        r,data=self.setup_env('example-key','six666')
        self.assertNotEqual(r.returncode,0)
        self.assertEqual(data,'')
    def test_blank_password_allowed_for_generation(self):
        r,data=self.setup_env('example-key','')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('OBS_PASSWORD=\n',data)

class PasswordGenerationTests(unittest.TestCase):
    def test_generate_only_for_missing_or_blank(self):
        script=(Path(__file__).parents[1]/'deploy/update.sh').read_text()
        code=script.split('import os, secrets\n',1)[1].split("\n')",1)[0]
        for value in (None,'','existing7'):
            env={k:v for k,v in os.environ.items() if k!='OBS_PASSWORD'}
            if value is not None: env['OBS_PASSWORD']=value
            result=subprocess.run([__import__('sys').executable,'-c','import os, secrets\n'+code],env=env,capture_output=True,text=True,check=True)
            if value: self.assertEqual(result.stdout,'')
            else: self.assertRegex(result.stdout.strip(),r'^[a-f0-9]{32}$')
