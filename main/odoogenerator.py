import json
import odoorpc
from odoorpc.rpc import build_opener, CookieJar, HTTPCookieProcessor
from urllib.request import HTTPSHandler
import os
import signal
import ssl
import sys
import subprocess
import time
from shutil import copy


class Connection:

    def load_config(self, version, file_path=False):
        if not file_path:
            local_path = os.path.join(
                self.config_path,
                'odoo_{}.json'.format(version)
            )
            if not os.path.exists(local_path):
                raise Exception('Unable to find configuration file for version: %s' % version)
            file_path = local_path
        f = open(file_path)
        data = json.load(f)
        f.close()
        return data

    def __init__(self, version):
        self.config_path = os.path.join(
            os.path.expanduser('~'),
            'Sviluppo',
            'srvmngt',
            'odoogenerator_config'
        )
        data = self.load_config(version)
        self.repositories = data["repositories"]
        self.options = data["options"]
        self.additional_options = data["additional_options"]
        self.queue_job = data["queue_job"]
        self.python = data["python"]
        self.path = os.path.expanduser('~')
        self.version = version
        self.venv_path = os.path.join(
            self.path,
            'Sviluppo',
            'Odoo',
            f'odoo{self.version}',
        )
        self.pg_bin_path = '/usr/lib/postgresql/15/bin/'
        # todo get from system function
        self.pid = False
        self.client = False

    def _create_venv(self, branch=False):
        venv_path = self.venv_path
        py_path = os.path.join(
            os.path.expanduser('~'),
            '.pyenv',
            'versions',
            self.python['version'],
            'bin',
            'python',
        )
        odoo_repo = 'https://github.com/OCA/OCB.git'
        if not os.path.isdir(venv_path):
            subprocess.Popen(['mkdir -p %s' % venv_path], shell=True).wait()
            subprocess.Popen(
                [
                    f'{py_path} -m venv {venv_path}'
                ],
                cwd=venv_path, shell=True
            ).wait()
        if not os.path.isdir(os.path.join(venv_path, 'odoo')):
            subprocess.Popen(
                [
                    f'git clone --branch {branch or self.version} {odoo_repo} --depth 1 odoo'
                ], cwd=venv_path, shell=True
            ).wait()
        elif branch:
            subprocess.Popen(
                [
                    f'git reset --hard origin/{self.version}',
                    f'git pull origin {branch} --depth 1',
                ], cwd=f'{venv_path}/odoo', shell=True
            ).wait()
        else:
            subprocess.Popen(
                [
                    f'git reset --hard origin/{self.version}',
                    f'git pull origin {self.version} --depth 1',
                    f'git reset --hard origin/{self.version}',
                ], cwd=f'{venv_path}/odoo', shell=True).wait()
        copy(
             os.path.join(
                self.config_path,
                f'requirements_{self.version}.txt'
             ),
             os.path.join(
                venv_path,
                'requirements.txt'
             ),
        )
        commands = [
            'bin/pip install -r requirements.txt --disable-pip-version-check',
            'bin/pip install -r odoo/requirements.txt --disable-pip-version-check',
            'cd odoo && ../bin/pip install -e .  --disable-pip-version-check',
        ]
        if self.version == '14.0':
            commands.append(["sed -i '/^chardet/d' odoo/requirements.txt"])
        for command in commands:
            subprocess.Popen(command, cwd=venv_path, shell=True).wait()
        repos = self.repositories
        for repo_name in repos:
            repo_url = repos.get(repo_name)
            if ' ' in repo_url:
                repo = repo_url.split(' ')[0]
                repo_version = repo_url.split(' ')[1]
            else:
                repo = repo_url
                repo_version = self.version
            if not os.path.isdir('%s/repos/%s' % (venv_path, repo_name)):
                subprocess.Popen([
                    f'git clone --branch {repo_version} {repo} {venv_path}/repos/{repo_name}',
                ], cwd=venv_path, shell=True
                ).wait()
            subprocess.Popen([
                f'git pull origin {repo_version}'
            ], cwd=f'{venv_path}/repos/{repo_name}', shell=True
            ).wait()
            if not any(x in repo_name for x in ['ait', 'reinova']):
                requirements_path = os.path.join(venv_path, 'repos', repo_name, 'requirements.txt')
                if os.path.isfile(requirements_path):
                    subprocess.Popen([
                        f'bin/pip install -r {requirements_path} --disable-pip-version-check',
                    ], cwd=venv_path, shell=True).wait()
        self.start_odoo(save_config=True)

    def start_odoo(self, update=False, save_config=False, extra_commands=False):
        """
        :param update: if True odoo will be updated with -u all and stopped
        :param save_config: if True start odoo, save .odoorc and stop
        :return: nothing
        """
        venv_path = self.venv_path
        options = self.options
        executable = 'openerp-server' if self.version in ['7.0', '8.0', '9.0'] else 'odoo'
        addons_path = ','.join(
            [f'{venv_path}/repos/{repo}' for repo in self.repositories if any(
                '__manifest__.py' in f for r, d, f in os.walk(
                    os.path.join(venv_path, 'repos', repo)
                )
            )
            ]
        )
        bash_command = f"""
./bin/{executable}
 {extra_commands or '-i base'}
 --addons-path={venv_path}/odoo/addons,{venv_path}/odoo/odoo/addons,{addons_path}
 --db_user={options['db_user']}
 --db_port={options['db_port']}
 --xmlrpc-port={options['http_port']}
 --log-handler={options['log_handler']}
 --limit-memory-hard={options['limit_memory_hard']}
 --limit-memory-soft={options['limit_memory_soft']}
 --limit-time-cpu={options['limit_time_cpu']}
 --limit-time-real={options['limit_time_real']}
 --load={options['server_wide_modules']}
        """
        if self.version != '7.0':
            bash_command += f"--data-dir={venv_path}/data_dir "
        if update:
            bash_command += " -u all -d %s --stop" % self.db
        if save_config:
            bash_command += f" -s --stop"
        process = subprocess.Popen(
            bash_command.split(), stdout=subprocess.PIPE, cwd=venv_path
        )
        self.pid = process.pid
        if save_config:
            process.wait()
            subprocess.Popen(
                ['cp ~/.odoorc ./'], shell=True, cwd=venv_path
            ).wait()
            # add additional_options and queue job
            if self.additional_options:
                for additional_option in self.additional_options:
                    subprocess.Popen(
                        [f'echo "{additional_option} = {self.additional_options[additional_option]}" >> .odoorc'],
                        shell=True, cwd=venv_path
                    ).wait()
            if self.queue_job:
                subprocess.Popen(
                    ['echo "[queue_job]" >> .odoorc'],
                    shell=True, cwd=venv_path
                ).wait()
                for job in self.queue_job:
                    subprocess.Popen(
                        [f'echo "{job} = {self.queue_job[job]}" >> .odoorc'],
                        shell=True, cwd=venv_path
                    ).wait()
        if update or extra_commands and 'stop' in extra_commands:
            process.wait()

    def create_it_po(self, module, repo):
        """
            crea un db vuoto ed installare il modulo richiesto per poi estrarre l'it.po
            :param str module: nome del modulo da tradurre
            :param str repo: nome del repository in cui si trova il modulo
        """
        commands = [
                f'dropdb --if-exists -p {self.options["db_port"]} demo10',
                f'createdb -p {self.options["db_port"]} demo10',
            ]
        for command in commands:
            subprocess.Popen(
                command,
                shell=True, cwd=self.venv_path
            ).wait()
        extra_commands = \
            f'-c .odoorc -i {module} --load-language=it_IT ' \
            f'-d demo10 ' \
            f'--stop'
        self.start_odoo(
            extra_commands=extra_commands
        )
        extra_commands = \
            f'-c .odoorc -l it_IT --modules={module} ' \
            f'-d demo10 ' \
            f'--i18n-export={self.venv_path}/repos/{repo}/{module}/i18n/it.po ' \
            f'--stop'
        self.start_odoo(
            extra_commands=extra_commands
        )

    ### WIP non in uso ###
    @staticmethod
    def _get_opener(verify_ssl=True, sessions=True):
        handlers = []
        if not verify_ssl:
            if (sys.version_info[0] == 2 and sys.version_info >= (2, 7, 9)) or (
                sys.version_info[0] == 3 and sys.version_info >= (3, 2, 0)
            ):
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                handlers.append(HTTPSHandler(context=context))
            else:
                print(
                    (
                        "verify_ssl could not be established for this "
                        "python version: %s"
                    )
                    % sys.version
                )
        if sessions:
            handlers.append(HTTPCookieProcessor(CookieJar()))
        opener = build_opener(*handlers)
        return opener

    def odoo_connect(
            self, db='demo10', user='admin', password='admin', address='localhost'):
        verify_ssl = True
        if self.options['http_port'] != 443:
            verify_ssl = False
        self.client = odoorpc.ODOO(
            host=address,
            opener=self._get_opener(verify_ssl=verify_ssl),
            port=self.options['http_port'],
            protocol="jsonrpc+ssl" if self.options['http_port'] == 443 else "jsonrpc",
            timeout=3600,
        )
        self.client.login(db=db, login=user, password=password)
        time.sleep(5)

    def stop_odoo(self):
        if self.pid:
            os.kill(self.pid, signal.SIGTERM)
            time.sleep(5)
