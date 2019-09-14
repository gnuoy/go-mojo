#!/usr/bin/env python3

import argparse
import datetime
import os
import json
import shutil
import subprocess
import sys
import yaml

PRE_REQ_PKGS = {
    'tox': 'Please install tox:\nsudo apt install tox',
    'bzr': 'Please install bzr:\nsudo apt install bzr',
    'juju': 'Please install juju:\nsudo snap install juju --classic',
}

CHARM_TEST_INFRA_REPO = ("https://github.com/openstack-charmers/"
                         "charm-test-infra.git")
OPENSTACK_MOJO_SPEC_REPO = ("https://github.com/openstack-charmers/"
                            "openstack-mojo-specs.git")
GOMOJO_ROOT = "/tmp/go-mojo"
MOJO_ROOT = GOMOJO_ROOT + '/mojo'
MOJO_VENV_ACTIVATE = GOMOJO_ROOT + "/activate"
CHARM_TEST_INFRA_DIR = GOMOJO_ROOT + '/charm-test-infra'
NOVARC_AUTO = "{}/novarc_auto".format(CHARM_TEST_INFRA_DIR)
OPENSTACK_MOJO_SPEC_DIR = GOMOJO_ROOT + '/openstack-mojo-specs'
CHARM_TEST_INFRA_TOX = CHARM_TEST_INFRA_DIR + '/tox.ini'
MOJO_ENV_FILE = "{home}/.mojo.yaml"
CLIENTS_VENV_DIR = CHARM_TEST_INFRA_DIR + '/.tox/clients'
MOJO_EXEC = CLIENTS_VENV_DIR + '/bin/mojo'


DEFAULT_MOJO_ENV = {
    'MOJO_OS_VIP00': "10.5.0.230",
    'MOJO_OS_VIP01': "10.5.0.231",
    'MOJO_OS_VIP02': "10.5.0.232",
    'MOJO_OS_VIP03': "10.5.0.233",
    'MOJO_OS_VIP04': "10.5.0.234",
    'MOJO_OS_VIP05': "10.5.0.235",
    'MOJO_OS_VIP06': "10.5.0.236",
    'MOJO_OS_VIP07': "10.5.0.237",
    'MOJO_OS_VIP08': "10.5.0.238",
    'MOJO_OS_VIP09': "10.5.0.239",
    'MOJO_OS_VIP10': "10.5.0.240",
    'MOJO_OS_VIP11': "10.5.0.241",
    'MOJO_OS_VIP12': "10.5.0.242",
    'MOJO_OS_VIP13': "10.5.0.243",
    'MOJO_OS_VIP14': "10.5.0.244",
    'MOJO_OS_VIP15': "10.5.0.245",
    'MOJO_OS_VIP16': "10.5.0.246",
    'MOJO_OS_VIP17': "10.5.0.247",
    'MOJO_OS_VIP18': "10.5.0.248",
    'MOJO_OS_VIP19': "10.5.0.249",
    'MOJO_OS_VIP20': "10.5.0.250",
    'CIDR_EXT': "10.5.0.0/24",  # Do not make too big used for subjAlt names
    'MOJO_PROJECT': "openstack",
    'MOJO_HOME': "~/mojo",
    'AMULET_HTTP_PROXY': 'http://squid.internal:3128',
    'AMULET_HTTPS_PROXY': 'http://squid.internal:3128'
}


def check_mojo_env_file():
    env_file = MOJO_ENV_FILE.format(home=os.environ['HOME'])
    if not os.path.exists(env_file):
        print("{} not found, creating".format(env_file))
        with open(env_file, 'w') as outfile:
            yaml.dump(DEFAULT_MOJO_ENV, outfile, default_flow_style=False)


def prereq_pkg_checks():
    checks_pass = True
    for cmd, msg in PRE_REQ_PKGS.items():
        try:
            subprocess.check_call(
                ['which', cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError:
            print(msg)
            checks_pass = False
    return checks_pass


def prereq_env_checks():
    if os.environ.get('OS_AUTH_URL'):
        return True
    else:
        print('OS_* variables not set in environment. Please source novarc '
              'for serverstack (probably ~/novarc) and rerun')
        return False


def prereq_juju_check():
    try:
        subprocess.check_call(['juju', 'status'])
    except subprocess.CalledProcessError:
        print('Error accessing juju model. Please ensure a juju model is in '
              'focus for mojo to deploy into')
        return False
    return True


def prereq_checks():
    return prereq_pkg_checks() and prereq_env_checks() and prereq_juju_check()


def recreate_mojo_venv():
    try:
        shutil.rmtree(GOMOJO_ROOT)
    except FileNotFoundError:
        # If dir doesn't exist no need to delete it.
        pass
    os.makedirs(CHARM_TEST_INFRA_DIR)
    subprocess.check_call([
        'git', 'clone', CHARM_TEST_INFRA_REPO, CHARM_TEST_INFRA_DIR])
    subprocess.check_call([
        'tox', '-c', CHARM_TEST_INFRA_TOX, '-e', 'clients'])
    subprocess.check_call([
        'ln', '-s', CHARM_TEST_INFRA_DIR + '/.tox/clients/bin/activate',
        MOJO_VENV_ACTIVATE])


def clone_openstack_mojo_specs(local_dir=None):
    try:
        shutil.rmtree(OPENSTACK_MOJO_SPEC_DIR)
    except FileNotFoundError:
        # If dir doesn't exist no need to delete it.
        pass
    if local_dir:
        shutil.copytree(local_dir, OPENSTACK_MOJO_SPEC_DIR, symlinks=True)
    else:
        subprocess.check_call([
            'git', 'clone', OPENSTACK_MOJO_SPEC_REPO, OPENSTACK_MOJO_SPEC_DIR])


def init_mojo(recreate_venv=False, local_spec_dir=None):
    if (not os.path.exists(MOJO_VENV_ACTIVATE)) or recreate_venv:
        recreate_mojo_venv()
    clone_openstack_mojo_specs(local_dir=local_spec_dir)
    return


def init_mojo_root(mojo_root, series):
    project_root = mojo_root + '/openstack'
    container_root = project_root + '/{}'.format(series)
    project_file = container_root + '/.project'
    try:
        os.makedirs(container_root)
    except FileExistsError:
        pass
    project_config = {
        "container_class": "containerless",
        "container_root": container_root,
        "project_root": project_root}
    with open(project_file, 'w') as outfile:
        json.dump(project_config, outfile)


def get_mojo_run_env(spec, mojo_root, series, workspace):
    project_root = mojo_root + '/openstack'
    container_root = project_root + '/{}'.format(series)
    mojo_local_dir = container_root + '/{}/local'.format(workspace)
    new_path = '{}/bin:{}'.format(CLIENTS_VENV_DIR, os.environ['PATH'])
    run_env = {
        'PATH': new_path,
        'MOJO_PROJECT': 'openstack',
        'MOJO_ROOT': mojo_root,
        'MOJO_STAGE': spec,
        'MOJO_WORKSPACE': workspace,
        'MOJO_SPEC': OPENSTACK_MOJO_SPEC_DIR,
        'MOJO_LOCAL_DIR': mojo_local_dir,
        'MOJO_SERIES': series}
    env_file = MOJO_ENV_FILE.format(home=os.environ['HOME'])
    if not os.path.exists(env_file):
        print("{} not found, exiting".format(env_file))
        sys.exit(1)
    with open(env_file, 'r') as outfile:
        contents = yaml.safe_load(outfile)
    run_env.update(contents)
    return run_env


def create_rerun_env(rerun_file, run_env):
    with open(rerun_file, 'w') as outfile:
        for key, value in run_env.items():
            outfile.write('export {}="{}"\n'.format(key, value))


def print_rerun_message(rerun_file, run_env, spec):
    print("\n\nIt loooks like your mojo run failed :-( ")
    print("\n* To rerun the whole spec using the existing environment:\n")
    print("    go-mojo.py -p -w {MOJO_WORKSPACE} -s {MOJO_SERIES} "
          "{MOJO_STAGE}".format(**run_env))
    print("\n\n* To rerun a specific step in the existing environment:\n")
    print("    source {}".format(rerun_file))
    print("    cd {}/{}".format(OPENSTACK_MOJO_SPEC_DIR, spec))
    print("\n    Check the manifest file for any options the script might ")
    print("    take and prepend them")
    print("\n    e.g. if the manifest contains the following line:")
    print("\n        verify config=simple_os_checks.py "
          "MACHINES='trusty:m1.small:2' CLOUDINIT_WAIT='600'")
    print("\n    Then run...")
    print("\n        MACHINES='trusty:m1.small:2' CLOUDINIT_WAIT='600' "
          "./simple_os_checks.py")
    print("\n* To use openstack cli for debugging:\n")
    print("    source {}".format(rerun_file))
    print("    source {}".format(NOVARC_AUTO))
    print("    openstack whatevs")


def run_mojo(spec, mojo_root, series, workspace):
    run_env = get_mojo_run_env(spec, mojo_root, series, workspace)
    rerun_file = ('{MOJO_ROOT}/{MOJO_PROJECT}/{MOJO_SERIES}/{MOJO_WORKSPACE}/'
                  'rerun_env').format(**run_env)
    my_env = os.environ.copy()
    my_env.update(run_env)
    cmd = [MOJO_EXEC, 'run']
    try:
        print(cmd)
        subprocess.check_call(cmd, env=my_env)
    except subprocess.CalledProcessError as e:
        create_rerun_env(rerun_file, run_env)
        print_rerun_message(rerun_file, run_env, spec)


def parse_args():
    """Parse command line arguments

    :returns: Dict of run settings
    :rtype: {}
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-p",
        "--preserve-venv",
        default=False,
        action='store_true',
        help=("Skip recreating venv. Speeds up deploy but may get stale zaza "
              "etc"))
    parser.add_argument(
        "-s",
        "--series",
        help="Ubuntu series to use eg bionic")
    parser.add_argument(
        "-w",
        "--workspace-name",
        help=("Specify workspace name to use. Useful when rerunning a spec "
              "and reusing the existing environment."))
    parser.add_argument(
        "-l",
        "--local-spec-dir",
        help="Use copy of openstack-mojo-specs in directory")
    parser.add_argument(
        "test_name",
        help="Full path to test eg specs/full_stack/next_designate_ha/stein")
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    prereq_checks() or sys.exit(1)
    recreate_venv = not args.preserve_venv
    init_mojo(recreate_venv=recreate_venv, local_spec_dir=args.local_spec_dir)
    check_mojo_env_file()
    init_mojo_root(MOJO_ROOT, args.series)
    workspace_name = args.workspace_name or \
        datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    run_mojo(args.test_name, MOJO_ROOT, args.series, workspace_name)
