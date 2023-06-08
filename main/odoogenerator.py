import json
import subprocess
import os
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
                    f'git clone --single-branch {odoo_repo} -b {branch or self.version}'
                    f' --depth 1 odoo'
                ], cwd=venv_path, shell=True
            ).wait()
        elif branch:
            subprocess.Popen(
                [
                    f"""
                    cd odoo
                    && git reset --hard origin/{self.version}
                    && git pull origin {branch}
                    """
                ], cwd=venv_path, shell=True
            ).wait()
        else:
            subprocess.Popen(
                [
                    'cd %s/odoo '
                    '&& git reset --hard origin/%s '
                    '&& git pull '
                    '&& git reset --hard origin/%s' % (
                        venv_path, self.version, self.version
                    )
                ], cwd=venv_path, shell=True).wait()
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
            'bin/python -m pip install --upgrade pip',
            'bin/pip install -r odoo/requirements.txt',
            'bin/pip install -r requirements.txt',
            'cd odoo && ../bin/pip install -e . ',
        ]
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
                    'git clone %s --single-branch -b %s --depth 1 '
                    '%s/repos/%s'
                    % (repo, repo_version, venv_path, repo_name)
                ], cwd=venv_path, shell=True
                ).wait()
            subprocess.Popen([
                'cd %s/repos/%s '
                '&& git remote set-branches --add origin %s '
                '&& git fetch '
                '&& git checkout origin/%s' % (
                    venv_path, repo_name,
                    repo_version,
                    repo_version)
            ], cwd=venv_path, shell=True
            ).wait()
            if 'ait' not in repo_name and 'reinova' not in repo_name:
                subprocess.Popen([
                    f'bin/pip install -r repos/{repo_name}/requirements.txt',
                ], cwd=venv_path, shell=True).wait()
        self.start_odoo(save_config=True)

    def start_odoo(self, update=False, save_config=False):
        """
        :param update: if True odoo will be updated with -u all and stopped
        :param save_config: if True start odoo, save .odoorc and stop
        :return: nothing
        """
        venv_path = self.venv_path
        options = self.options
        executable = 'openerp-server' if self.version in ['7.0', '8.0', '9.0'] else 'odoo'
        addons_path = ','.join(
            [f'{venv_path}/repos/{repo}' for repo in self.repositories]
        )
        bash_command = f"""
./bin/{executable}
 -i base
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
        if update:
            process.wait()
