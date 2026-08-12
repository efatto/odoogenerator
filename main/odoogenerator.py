#!/usr/bin/env python

from odoorpc.rpc import build_opener, CookieJar, HTTPCookieProcessor
from shutil import copy
from urllib.request import HTTPSHandler
import argparse
import json
import odoorpc
import os
import signal
import ssl
import subprocess
import sys
import time
import tempfile
import yaml

UV_PROJECT_ENVIRONMENT = os.environ.get("UV_PROJECT_ENVIRONMENT", ".venv")

class OdooGenerator:
    def load_config(self, version, file_path=False):
        if not file_path:
            local_path = os.path.join(self.config_path, f"odoo_{version}.json")
            if not os.path.exists(local_path):
                raise Exception(
                    f"Unable to find configuration file for version: {version}"
                )
            file_path = local_path
        f = open(file_path)
        data = json.load(f)
        f.close()

        # Update URLs for repositories present in repos.yml
        config_path = os.path.join(
            os.path.expanduser('~'),
            'Sviluppo',
            'make_python_wheels',
            'repos_gitaggregate',
            version,
            "repos.yml")
        if os.path.exists(config_path):
            with open(config_path, "r") as stream:
                try:
                    parts = yaml.safe_load(stream) or {}
                except yaml.YAMLError as exc:
                    print(exc)
                    parts = {}
            repos_in_yml = [x.split("/")[-1].split("_")[0] for x in parts]
            for repo_name in data.get("repositories", {}):
                if repo_name in repos_in_yml:
                    url = data["repositories"][repo_name]
                    if url.startswith("https://github.com/OCA/"):
                        data["repositories"][repo_name] = url.replace(
                            "https://github.com/OCA/", "git@github.com:efatto/"
                        )
        return data

    @staticmethod
    def get_repositories_and_branches(branch=False, singlerepo=False, config_list=None):
        if not config_list:
            config_list = ["repos.yml", "repos_custom.yml"]  # , "repos_ocb.yml"]
        for config in config_list:
            print(branch)
            print(singlerepo)
            gitaggregate = False
            if config == "repos.yml":
                gitaggregate = True
            config_path = os.path.join(
                os.path.expanduser('~'),
                'Sviluppo',
                'make_python_wheels',
                'repos_gitaggregate',
                branch,
                config)
            with open(config_path, "r") as stream:
                try:
                    parts = yaml.safe_load(stream) or {}
                except yaml.YAMLError as exc:
                    print(exc)
            if singlerepo:
                part = [x for x in parts if
                        singlerepo == x.split("/")[-1].split("_")[0]]
                if part:
                    part = part[0]
                    repo, branch = part.split("/")[-1].split("_")
                    protocol = parts[part].get("remotes").get("efatto")
                    if protocol:
                        protocol = protocol.replace(
                            "git+ssh://", ""
                        )
                        yield repo, branch, protocol, gitaggregate, parts, part
            else:
                for part in parts:
                    repo, branch = part.split("/")[-1].split("_")
                    protocol = parts[part].get("remotes").get("efatto")
                    if protocol:
                        protocol = protocol.replace(
                            "git+ssh://", ""
                        )
                        yield repo, branch, protocol, gitaggregate, parts, part

    def __init__(self, version):
        self.config_path = os.path.join(
            os.path.expanduser("~"), "Sviluppo", "srvmngt", "odoogenerator_config"
        )
        data = self.load_config(version)
        self.repositories = data["repositories"]
        self.private_repositories = data["private-repositories"]
        self.all_repositories = dict(**self.repositories, **self.private_repositories)
        self.options = data["options"]
        self.additional_options = data["additional_options"]
        self.python = data["python"]
        self.path = os.path.expanduser("~")
        self.version = version
        self.base_path = os.path.join(self.path, "Sviluppo", "Odoo")
        self.venv_path = os.path.join(
            self.base_path,
            f"odoo{self.version}",
        )
        self.pg_bin_path = "/usr/lib/postgresql/14/bin/"
        # todo get from system function
        self.pid = False
        self.client = False

    def git_aggregate(self, branch, singlerepo, config_list):
        gitaggregate_target = "efatto"
        for repo, branch, repo_url, gitagg, parts, part in self.get_repositories_and_branches(
            branch, singlerepo, config_list
        ):
            tmp_filename = tempfile.mktemp(suffix=".yml")
            try:
                with open(tmp_filename, "w+") as writer:
                    file_dict = [{x: parts[x]} for x in parts if x == part][0]
                    yaml.dump(file_dict, writer)
                    bash_command = [
                        f'sed -i "s/target: pretecno/target: {gitaggregate_target}/" '
                        f'{tmp_filename}',
                        f"gitaggregate -p -c {tmp_filename}",
                        f"sed -i 's/target: {gitaggregate_target}/target: pretecno/' "
                        f"{tmp_filename}",
                    ]
                    for command in bash_command:
                        subprocess.Popen(
                            command, stdout=subprocess.PIPE, shell=True
                        ).wait()
            finally:
                os.unlink(tmp_filename)

    def create_venv(self, branch=False, private=False, gitaggregate="no", recreate=False):
        # todo add option to recreate venv (eg. to change python version) by removing
        #  .python-version and pyproject.toml (and removing folder venv_path/bin?)
        venv_path = self.venv_path
        bin_path = os.path.join(venv_path, UV_PROJECT_ENVIRONMENT, "/bin/")
        if not os.path.isdir(venv_path):
            os.makedirs(venv_path)
        odoo_repo = "https://github.com/OCA/OCB.git"
        if not os.path.isfile(os.path.join(venv_path, "pyproject.toml")) or recreate:
            for command in [
                f"uv init --directory {venv_path} --python "
                f"'python=={self.python['version']}'",
                f"uv venv --python {self.python['version']}",
            ]:
                subprocess.Popen(
                    command,
                    shell=True,
                    cwd=venv_path,  # self.base_path?
                ).wait()
        python_version_file = os.path.join(venv_path, ".python-version")
        if not os.path.isfile(python_version_file) or recreate:
            with open(python_version_file, "w") as writer:
                writer.write(f"{self.python['version']}")
            writer.close()
        if not os.path.isdir(os.path.join(venv_path, "odoo")):
            subprocess.Popen(
                [
                    f"git clone --branch {branch or self.version} {odoo_repo} "
                    f"--depth 1 odoo"
                ],
                cwd=venv_path,
                shell=True,
            ).wait()
        else:
            # I presume odoo branch is always the same
            subprocess.Popen(
                [
                    "git pull --rebase",
                ],
                cwd=f"{venv_path}/odoo",
                shell=True,
            ).wait()
        uv_override_deps = []
        if self.version in ["14.0", "15.0", "16.0"]:
            uv_override_deps.append("XlsxWriter==3.2.9")
        if self.version in ["16.0", "17.0"]:
            uv_override_deps.extend(
                [
                    "Werkzeug==2.0.2",
                    "lxml==4.9.3",
                    "gevent==22.10.2",
                    "greenlet==2.0.2",
                    "docutils==0.18.1",
                ]
            )
        if uv_override_deps:
            if "tool.uv" not in open(os.path.join(venv_path, "pyproject.toml")).read():
                with open(os.path.join(venv_path, "pyproject.toml"), "a") as f:
                    f.write("[tool.uv]\n")
                    f.write(f"override-dependencies = {str(uv_override_deps)} ")
                    f.close()
        copy(
            os.path.join(self.config_path, f"requirements_{self.version}.txt"),
            os.path.join(venv_path, "requirements.txt"),
        )
        commands = [
            f"uv add --active --frozen -r {self.venv_path}/requirements.txt",
            f"uv add --active --frozen -r {self.venv_path}/odoo/requirements.txt",
            f"uv pip install -e {self.venv_path}/odoo",
        ]
        for command in commands:
            subprocess.Popen(command, cwd=bin_path, shell=True).wait()
        repos = self.repositories
        if private:
            repos = self.all_repositories
        for repo_name in repos:
            repo_url = repos.get(repo_name)
            if " " in repo_url:
                repo, repo_version = repo_url.split(" ")
            else:
                repo = repo_url
                repo_version = self.version
            if not os.path.isdir("%s/repos/%s" % (venv_path, repo_name)):
                subprocess.Popen(
                    [
                        f"git clone --branch {repo_version} {repo} "
                        f"{venv_path}/repos/{repo_name}",
                    ],
                    cwd=venv_path,
                    shell=True,
                ).wait()
            if gitaggregate == "yes":
                self.git_aggregate(
                    repo_version, repo_name, config_list=["repos.yml"])
            if os.path.isdir("%s/repos/%s" % (venv_path, repo_name)):
                # Check if current remote is different from config repo
                check_remote_cmd = "git remote get-url origin"
                process = subprocess.Popen(
                    check_remote_cmd,
                    cwd=f"{venv_path}/repos/{repo_name}",
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, _ = process.communicate()
                current_remote = stdout.decode().strip()
                if current_remote and current_remote != repo:
                    # Set current remote as upstream and new repo as origin
                    for command in [
                        "git remote rename origin upstream",
                        f"git remote add origin {repo}",
                        "git fetch origin",
                        f"git branch --set-upstream-to=origin/{repo_version} {repo_version}",
                    ]:
                        subprocess.Popen(
                            command,
                            cwd=f"{venv_path}/repos/{repo_name}",
                            shell=True,
                        ).wait()

                for command in [
                    "git fetch origin",
                    f"git reset --hard origin/{repo_version}",
                    f"git checkout {repo_version}",
                    "git pull --rebase",
                ]:
                    subprocess.Popen(
                        command,
                        cwd=f"{venv_path}/repos/{repo_name}",
                        shell=True,
                    ).wait()
            requirements_path = os.path.join(
                venv_path, "repos", repo_name, "requirements.txt"
            )
            if os.path.isfile(requirements_path):
                print(f"Installing requirements from {requirements_path}")
                subprocess.Popen(
                    [
                        f"uv add --active --frozen -r {requirements_path}",
                    ],
                    cwd=venv_path,
                    shell=True,
                ).wait()
        # ensure python libraries are installed at required version
        commands = [
            f"uv add --active --frozen -r requirements.txt",
        ]
        for command in commands:
            subprocess.Popen(command, cwd=venv_path, shell=True).wait()
        self.start_odoo(save_config=True)

    def start_odoo(self, save_config=False, extra_commands=False):
        """
        :param save_config: if True start odoo, save .odoorc and stop
        :param extra_commands: command to pass after executable
        :return: nothing
        """
        venv_path = self.venv_path
        options = self.options
        executable = (
            "openerp-server" if self.version in ["7.0", "8.0", "9.0"] else "odoo-bin"
        )
        addons_path = ",".join(
            [
                f"{venv_path}/repos/{repo}"
                for repo in self.all_repositories
                if any(
                    "__manifest__.py" in f
                    for r, d, f in os.walk(os.path.join(venv_path, "repos", repo))
                )
            ]
        )
        bash_command = f"""
{venv_path}/{UV_PROJECT_ENVIRONMENT}/bin/python
{venv_path}/odoo/{executable}
 {extra_commands or '-i base'}
 --addons-path={venv_path}/odoo/addons,{venv_path}/odoo/odoo/addons,{addons_path}
 --db_user={options['db_user']}
 --db_port={options['db_port']}
 --http-port={options['http_port']}
 --log-handler={options['log_handler']}
 --limit-memory-hard={options['limit_memory_hard']}
 --limit-memory-soft={options['limit_memory_soft']}
 --limit-time-cpu={options['limit_time_cpu']}
 --limit-time-real={options['limit_time_real']}
 --load={options['server_wide_modules']}
 -c {venv_path}/.odoorc
        """
        if self.version != "7.0":
            bash_command += f"--data-dir={venv_path}/data_dir "
        if save_config:
            bash_command += f" -s --stop"
        process = subprocess.Popen(
            bash_command.split(), stdout=subprocess.PIPE, cwd=venv_path
        )
        self.pid = process.pid
        if save_config:
            process.wait()
            if os.path.isfile(os.path.join(self.path, ".odoorc")):
                # move .odoorc from user home to Odoo path
                subprocess.Popen(["mv ~/.odoorc ./"], shell=True, cwd=venv_path).wait()
            # remove line with osv_memory_age_limit
            subprocess.Popen(
                ['sed -i "/^osv_memory_age_limit/d" .odoorc'], shell=True, cwd=venv_path
            ).wait()
            # read .odoorc and add additional options
            with open(os.path.join(venv_path, ".odoorc")) as f:
                odoorc_text = f.read()
                f.close()
            if self.additional_options:
                for additional_option in self.additional_options:
                    if additional_option not in odoorc_text:
                        subprocess.Popen(
                            [
                                f'echo "{additional_option} = '
                                f'{self.additional_options[additional_option]}"'
                                f" >> .odoorc"
                            ],
                            shell=True,
                            cwd=venv_path,
                        ).wait()
        if extra_commands and "stop" in extra_commands:
            process.wait()

    def create_it_po(self, module, repo):
        """
        crea un db vuoto ed installa il modulo richiesto per poi estrarre l'it.po
        per la versione attualmente attiva in __init__
        :param str module: nome del modulo da tradurre
        :param str repo: nome del repository in cui si trova il modulo
        """
        commands = [
            f'dropdb --if-exists -p {self.options["db_port"]} demo10',
            f'createdb -p {self.options["db_port"]} demo10',
        ]
        for command in commands:
            subprocess.Popen(command, shell=True, cwd=self.venv_path).wait()
        extra_commands = (
            f"-c .odoorc -i {module} --load-language=it_IT -d demo10 --stop"
        )
        self.start_odoo(extra_commands=extra_commands)
        extra_commands = (
            f"-c {self.venv_path}/.odoorc -l it_IT --db_port={self.options['db_port']} "
            f"--modules={module} -d demo10 "
            f"--i18n-export={self.venv_path}/repos/{repo}/{module}/i18n/it.po "
            f"--stop"
        )
        self.start_odoo(extra_commands=extra_commands)

    def create_it_po_for_repo(self, repo):
        # recreate all it.po files for the selected repo
        for dirname in os.listdir(
            os.path.join(self.venv_path, "repos", repo)
        ):
            if os.path.isdir(os.path.join(self.venv_path, "repos", repo, dirname)):
                if not dirname.startswith((".", "_", "setup")):
                    self.create_it_po(dirname, repo)

    # WIP non in uso ###
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
        self, db="demo10", user="admin", password="admin", address="localhost"
    ):
        verify_ssl = True
        if self.options["http_port"] != 443:
            verify_ssl = False
        self.client = odoorpc.ODOO(
            host=address,
            opener=self._get_opener(verify_ssl=verify_ssl),
            port=self.options["http_port"],
            protocol="jsonrpc+ssl" if self.options["http_port"] == 443 else "jsonrpc",
            timeout=3600,
        )
        self.client.login(db=db, login=user, password=password)
        time.sleep(5)

    def stop_odoo(self):
        if self.pid:
            os.kill(self.pid, signal.SIGTERM)
            time.sleep(5)


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(
            description="Odoo Generator: download sources and create a virtualenv"
        )
        parser.add_argument(
            "-V",
            "--version",
            help="Odoo version",
            choices=["12.0", "14.0", "16.0", "17.0", "18.0", "19.0"],
            default="14.0",
        )
        parser.add_argument(
            "-P",
            "--private",
            help="Odoo private repositories",
            choices=['yes'],
        )
        parser.add_argument(
            "-T",
            "--translate-repo",
            help="Translate repository",
        )
        parser.add_argument(
            "-S",
            "--save-only",
            help="Save only",
            choices=['yes'],
        )
        parser.add_argument(
            "-G",
            "--gitaggregate",
            help="Gitaggregate",
            choices=['yes'],
            default='no',
        )
        args = parser.parse_args()
        o = OdooGenerator(version=args.version)
        if args.translate_repo:
            o.create_it_po_for_repo(args.translate_repo)
        elif args.save_only:
            o.start_odoo(save_config=True)
        else:
            o.create_venv(private=args.private, gitaggregate=args.gitaggregate)
    except Exception as e:
        print("Error: " + str(e))
