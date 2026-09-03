#!/usr/bin/env python
import subprocess
from pathlib import Path

from odoorpc.rpc import build_opener, CookieJar, HTTPCookieProcessor
from configparser import ConfigParser
from shutil import copy
from urllib.request import HTTPSHandler
import argparse
import json
import odoorpc
import os
import signal
import ssl
from subprocess import PIPE, Popen, run
import sys
import time
import tempfile
import yaml

UV_PROJECT_ENVIRONMENT = os.environ.get("UV_PROJECT_ENVIRONMENT", "venv")

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
        self.project_path = os.path.join(
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
            tmp_filename = tempfile.mkstemp(suffix=".yml")
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
                        run(
                            command, stdout=PIPE, shell=True
                        )
            finally:
                os.unlink(tmp_filename)

    def create_venv(self, branch=False, private=False, gitaggregate="no", recreate=False):
        # todo add option to recreate venv (eg. to change python version) by removing
        #  .python-version and pyproject.toml (and removing folder project_path/bin?)
        project_path = self.project_path
        env_path = os.path.join(project_path, UV_PROJECT_ENVIRONMENT)
        bin_path = os.path.join(env_path, "bin")
        if not os.path.isdir(project_path):
            os.makedirs(project_path)
        odoo_repo = "https://github.com/OCA/OCB.git"
        if (
            not os.path.isfile(os.path.join(project_path, "pyproject.toml"))
            or not os.path.isfile(bin_path)
            or recreate
        ):
            if recreate:
                os.remove(os.path.join(project_path, "pyproject.toml"))
            for command in [
                f"uv init --directory {project_path} --python "
                f"'python=={self.python['version']}'",
                f"uv venv {UV_PROJECT_ENVIRONMENT} {'--clear' if recreate else ''} "
                f"--directory {project_path} --python {self.python['version']}",
            ]:
                run(
                    command,
                    shell=True,
                    cwd=project_path,
                )
        python_version_file = os.path.join(project_path, ".python-version")
        if not os.path.isfile(python_version_file) or recreate:
            with open(python_version_file, "w") as writer:
                writer.write(f"{self.python['version']}")
            writer.close()
        if not os.path.isdir(os.path.join(project_path, "odoo")):
            run(
                [
                    f"git clone --branch {branch or self.version} {odoo_repo} "
                    f"--depth 1 odoo"
                ],
                cwd=project_path,
                shell=True,
            )
        else:
            # I presume odoo branch is always the same
            run(
                [
                    "git pull --rebase",
                ],
                cwd=f"{project_path}/odoo",
                shell=True,
            )
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
            if "tool.uv" not in open(os.path.join(project_path, "pyproject.toml")).read():
                with open(os.path.join(project_path, "pyproject.toml"), "a") as f:
                    f.write("[tool.uv]\n")
                    f.write(f"override-dependencies = {str(uv_override_deps)} ")
                    f.close()
        copy(
            os.path.join(self.config_path, f"requirements_{self.version}.txt"),
            os.path.join(project_path, "requirements.txt"),
        )
        commands = [
            f"uv add --active --frozen -r {self.project_path}/requirements.txt",
            f"uv add --active --frozen -r {self.project_path}/odoo/requirements.txt",
            f"uv add --active --frozen --editable {self.project_path}/odoo --no-workspace",
        ]
        for command in commands:
            run(command, cwd=project_path, shell=True)
        repos = self.repositories
        if private:
            repos = self.all_repositories
        for repo_name in repos:
            cwd_path = f"{project_path}/repos/{repo_name}"
            repo_url = repos.get(repo_name)
            if " " in repo_url:
                repo, repo_version = repo_url.split(" ")
            else:
                repo = repo_url
                repo_version = self.version
            if not os.path.isdir("%s/repos/%s" % (project_path, repo_name)):
                run(
                    [
                        f"git clone --branch {repo_version} {repo} {cwd_path}",
                    ],
                    cwd=project_path,
                    shell=True,
                )
            if gitaggregate == "yes":
                self.git_aggregate(
                    repo_version, repo_name, config_list=["repos.yml"])
            if os.path.isdir("%s/repos/%s" % (project_path, repo_name)):
                # Check if current remote is different from config repo
                check_remote_cmd = "git remote get-url origin"
                process = subprocess.run(
                    check_remote_cmd,
                    cwd=cwd_path,
                    shell=True,
                    stdout=PIPE,
                    text=True,
                )
                current_remote = process.stdout.strip()
                if current_remote and current_remote != repo:
                    # Set current remote as upstream and new repo as origin
                    for command in [
                        "git remote rename origin upstream",
                        f"git remote add origin {repo}",
                        "git fetch origin",
                        f"git branch --set-upstream-to=origin/{repo_version} {repo_version}",
                    ]:
                        run(
                            command,
                            cwd=cwd_path,
                            shell=True,
                        )

                for command in [
                    "git fetch origin",
                    f"git reset --hard origin/{repo_version}",
                    f"git checkout {repo_version}",
                    "git pull",
                ]:
                    print(
                        f"Running command: {command} in {cwd_path}")
                    run(
                        command,
                        cwd=cwd_path,
                        shell=True,
                    )
            requirements_path = os.path.join(
                project_path, "repos", repo_name, "requirements.txt"
            )
            if os.path.isfile(requirements_path):
                print(f"Installing requirements from {requirements_path}")
                run(
                    [
                        f"uv add --active --frozen -r {requirements_path}",
                    ],
                    cwd=project_path,
                    shell=True,
                )
        # ensure python libraries are installed at required version
        commands = [
            "uv add --active --frozen -r requirements.txt",
            "uv sync --active",
        ]
        for command in commands:
            run(
                command,
                cwd=project_path,
                shell=True,
            )
        self.start_odoo(save_config=True)
        print(f"Python libraries installed successfully in env {env_path}.")

    def start_odoo(self, save_config=False, extra_commands=False):
        """
        :param save_config: if True start odoo, save .odoorc and stop
        :param extra_commands: command to pass after executable
        :return: nothing
        """
        project_path = self.project_path
        env_path = os.path.join(project_path, UV_PROJECT_ENVIRONMENT)
        options = self.options
        executable = (
            "openerp-server" if self.version in ["7.0", "8.0", "9.0"] else "odoo-bin"
        )
        addons_path = ",".join(
            [
                f"{project_path}/repos/{repo}"
                for repo in self.all_repositories
                if any(
                    "__manifest__.py" in f
                    for r, d, f in os.walk(os.path.join(project_path, "repos", repo))
                )
            ]
        )
        bash_command = (
            f"{env_path}/bin/python "
            f"{project_path}/odoo/{executable} "
            f"{extra_commands or '-i base'} "
            f"--addons-path={project_path}/odoo/addons,{project_path}/odoo/odoo/addons,"
            f"{addons_path} "
            f"--db_user={options['db_user']} "
            f"--db_port={options['db_port']} "
            f"--http-port={options['http_port']} "
            f"--log-handler={options['log_handler']} "
            f"--limit-memory-hard={options['limit_memory_hard']} "
            f"--limit-memory-soft={options['limit_memory_soft']} "
            f"--limit-time-cpu={options['limit_time_cpu']} "
            f"--limit-time-real={options['limit_time_real']} "
            f"--load={options['server_wide_modules']} "
            f"-c {project_path}/.odoorc "
        )
        if self.version != "7.0":
            bash_command += f"--data-dir={project_path}/data_dir "
        if save_config:
            bash_command += f" -s --stop"
        env = os.environ.copy()
        env.update({
            "VIRTUAL_ENV": env_path,
            "UV_PROJECT_ENVIRONMENT": env_path,
            "PWD": env_path,
            "PYTHONPATH": os.path.join(env_path, "bin", "python"),
            "PATH": ":".join(
                [
                    env_path,
                    os.path.join(env_path, "bin"),
                    "/bin",
                    "/usr/bin",
                    os.path.join(os.path.expanduser("~"), ".local", "bin"),
                ]
            )
        })
        run(
            bash_command, shell=True, env=env, cwd=project_path
        )
        if save_config:
            if os.path.isfile(os.path.join(self.path, ".odoorc")):
                # move default .odoorc from user home to Odoo path
                run(["mv ~/.odoorc ./"], shell=True, cwd=project_path)
            # remove line with osv_memory_age_limit if exists
            config = ConfigParser()
            path = Path(project_path)
            config.read(path / ".odoorc")
            if config.get("options", "osv_memory_age_limit", fallback=False):
                config.remove_option("options", "osv_memory_age_limit")
                with open(path / ".odoorc", "w") as configfile:
                    config.write(configfile)
            # add additional options
            if self.additional_options:
                for additional_option in self.additional_options:
                    if additional_option not in config.get("options", additional_option, fallback=False):
                        config.set(
                            "options",
                            additional_option,
                            self.additional_options[additional_option],
                        )
                        with open(path / ".odoorc", "w") as configfile:
                            config.write(configfile)
        print("Updated .odoorc file with additional options.")

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
            run(command, shell=True, cwd=self.project_path)
        extra_commands = (
            f"-c .odoorc -i {module} --load-language=it_IT -d demo10 --stop"
        )
        self.start_odoo(extra_commands=extra_commands)
        extra_commands = (
            f"-c {self.project_path}/.odoorc -l it_IT --db_port={self.options['db_port']} "
            f"--modules={module} -d demo10 "
            f"--i18n-export={self.project_path}/repos/{repo}/{module}/i18n/it.po "
            f"--stop"
        )
        self.start_odoo(extra_commands=extra_commands)

    def create_it_po_for_repo(self, repo):
        # recreate all it.po files for the selected repo
        for dirname in os.listdir(
            os.path.join(self.project_path, "repos", repo)
        ):
            if os.path.isdir(os.path.join(self.project_path, "repos", repo, dirname)):
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
        parser.add_argument(
            "-R",
            "--recreate",
            help="Recreate env",
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
            o.create_venv(
                private=args.private,
                gitaggregate=args.gitaggregate,
                recreate=args.recreate == 'yes',
            )
    except Exception as e:
        print("Error: " + str(e))
