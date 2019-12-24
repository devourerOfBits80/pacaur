#!/usr/bin/python

# Copyright: (c) 2019, Tomasz Choroba <tomasz.choroba@yahoo.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: pacaur

short_description: Manage Arch Linux OS packages with the AUR support

version_added: "2.9"

description:
    - Manage packages distributed by the official Arch Linux repositories
      together with support for the Arch User Repository (AUR).

options:
    name:
        description:
            - Name or name list of the package(s) to install, upgrade or
              remove. Cannot be used in combination with C(upgrade) option.
        aliases: [ package, pkg ]
        type: list
        elements: str
    state:
        description:
            - Desired state of the package(s).
        default: present
        type: str
        choices: [ absent, latest, present ]
    upgrade:
        description:
            - Whether or not to upgrade the whole system. Cannot be used in
              combination with C(name) option.
        default: no
        type: bool
    update_cache:
        description:
            - Whether or not to refresh the master package databases for the
              official repositories. This option can be execute as a part of
              the C(name) or C(upgrade) option and also as a separate step.
        aliases: [ update-cache ]
        default: no
        type: bool
    force:
        description:
            - Whether or not to force required action. During the package(s)
              installing or updating, responsible for enforcing the package
              details checking in the official repositories. During the
              package(s) removing, responsible for skipping all dependencies
              checking, equivalent of C(extra_args)='--nodeps --nodeps'. During
              the cache updating, responsible for refreshing all package
              databases, even if they appear to be up-to-date, equivalent of
              C(extra_args)='--refresh --refresh'.
        default: no
        type: bool
    extra_args:
        description:
            - Additional option(s) that should be passed to the package
              manager.
        default:
        type: str

author:
    - Tomasz Choroba (@devourerOfBits80)
'''

EXAMPLES = '''
# Install package from the official repositories
- name: Install package foo
  pacaur:
    name:
      - foo
    state: present

# Install package from file
- name: Install package bar from file
  pacaur:
    name:
      - ~/bar-1.0.0-1-any.pkg.tar.xz
    state: present

# Install packages from the official repositories and from file
- name: Install package foo and package bar from file
  pacaur:
    name:
      - foo
      - ~/bar-1.0.0-1-any.pkg.tar.xz
    state: present

# Install package from the AUR
- name: Install package aur-foo
  pacaur:
    name:
      - aur-foo
    state: present
  become: yes
  become_user: non-root-user

# Install package from the AUR without PGP signatures verification
- name: Install package aur-foo with skipping of PGP check
  pacaur:
    name:
      - aur-foo
    state: present
    extra_args: --skippgpcheck
  become: yes
  become_user: non-root-user

# Install packages from the official repositories and from the AUR (only
# available if the pacman's wrapper eg. yay, pikaur or trizen is already
# installed)
- name: Install packages foo and aur-foo
  pacaur:
    name:
      - foo
      - aur-foo
    state: present
  become: yes
  become_user: non-root-user

# Upgrade package from the official repositories
- name: Upgrade package foo
  pacaur:
    name:
      - foo
    state: latest
    update_cache: yes

# Upgrade package from the AUR
- name: Upgrade package aur-foo
  pacaur:
    name:
      - aur-foo
    state: latest
  become: yes
  become_user: non-root-user

# Remove desired packages
- name: Remove packages foo, bar and aur-foo
  pacaur:
    name:
      - foo
      - bar
      - aur-foo
    state: absent

# Recursively remove desired package
- name: Remove package foo including all its dependencies
  pacaur:
    name:
      - foo
    state: absent
    extra_args: '-s -n'

# Force package removing
- name: Execute the equivalent of 'I(pacman -Rdd foo)' command
  pacaur:
    name:
      - foo
    state: absent
    force: yes

# Refresh the master package databases for the official repositories
- name: Execute the equivalent of 'I(pacman -Sy)' command as a separate step
  pacaur:
    update_cache: yes

# Refresh the master package databases, even if they appear up-to-date
- name: Execute the equivalent of 'I(pacman -Syy)' command as a separate step
  pacaur:
    update_cache: yes
    force: yes

# Upgrade all packages from the official repositories
- name: Execute the equivalent of 'I(pacman -Syu)' command as a separate step
  pacaur:
    upgrade: yes
    update_cache: yes

# Upgrade the whole system (only available if the pacman's wrapper eg. yay,
# pikaur or trizen is already installed)
- name: Execute the equivalent of eg. 'I(yay -Syu)' command as a separate step
  pacaur:
    upgrade: yes
    update_cache: yes
  become: yes
  become_user: non-root-user
'''

RETURN = '''
msg:
    description: result of action that has been taken
    returned: always
    type: str
handler:
    description: path to the system application that executed required action
    returned: when action is related to install or upgrade package(s)
    type: str
'''


import json
import os
import re
import tarfile
import tempfile
import urllib.parse

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import open_url


package_version_pattern = '-[0-9].*$'

state_equivalents = {
    'absent': 'removed',
    'present': 'installed',
    'latest': 'updated'
}

pacman_wrappers = {
    'yay': {
        'install': ['-S', '--needed', '--noconfirm', '--noprogressbar', '--cleanafter'],
        'upgrade': ['-S', '-u', '-q', '--noconfirm']
    },
    'pikaur': {
        'install': ['-S', '--needed', '--noconfirm', '--noprogressbar', '--noedit'],
        'upgrade': ['-S', '-u', '-q', '--noconfirm']
    },
    'trizen': {
        'install': ['-S', '--needed', '--noconfirm', '--noprogressbar', '--noedit'],
        'upgrade': ['-S', '-u', '-q', '--noconfirm']
    }
}


def get_pacman_wrapper(module):
    '''
    Retrieve one of the predefined pacman's wrapper to have the direct AUR support.
    '''
    pacman_wrapper = None

    for item in pacman_wrappers:
        wrapper = module.get_bin_path(item)

        if wrapper:
            pacman_wrapper = wrapper
            break

    return pacman_wrapper


def get_pacman_wrapper_command(wrapper, upgrade_mode=False):
    '''
    Retrieve command to install or upgrade packages with using the wrapper.
    '''
    cmd = [wrapper]
    action = 'upgrade' if upgrade_mode else 'install'
    cmd.extend(pacman_wrappers[wrapper.split('/')[-1]][action])
    return cmd


def get_current_user_name(module):
    '''
    Retrieve name of the current user.
    '''
    user_name = 'root'
    rc, stdout, _ = module.run_command('whoami', check_rc=False)

    if rc == 0:
        user_name = stdout.strip()

    return user_name


def get_handler(module, pacman):
    '''
    Retrieve package manager to handle the required action(s).
    '''
    user = get_current_user_name(module)
    handler = pacman

    if user != 'root':
        wrapper = get_pacman_wrapper(module)

        if wrapper is not None:
            handler = wrapper

    return handler


def split_extra_args(extra_args_str):
    '''
    Split the string of extra arguments.
    '''
    extra_args = []

    if extra_args_str:
        extra_args = extra_args_str.split()

    return extra_args


def refresh_package_databases(module, pacman, result):
    '''
    Refresh the master package databases for the official repositories.
    '''
    handler = get_handler(module, pacman)

    if handler == pacman and get_current_user_name(module) != 'root':
        result['msg'] = 'could not refresh the master package databases as a non-root user when no pacman\'s ' \
            'wrapper is installed'
        module.fail_json(**result)

    params = module.params
    cmd = [handler, '-S', '-y']

    if params['force']:
        cmd.append('-y')

    if not (params['name'] or params['upgrade']):
        cmd.extend(split_extra_args(params['extra_args']))

    rc, _, stderr = module.run_command(cmd, check_rc=False)

    if rc != 0:
        result['msg'] = 'could not refresh the master package databases: {}'.format(stderr)
        module.fail_json(**result)


def return_update_cache_result(module, submsg, result):
    '''
    Prepare and return result for the update cache option.
    '''
    result['changed'] = True
    result['msg'] = 'master package databases {} refreshed'.format(submsg)
    module.exit_json(**result)


def return_upgrade_result(module, submsg, result):
    '''
    Prepare and return result for the upgrade option.
    '''
    result['changed'] = True
    result['msg'] = 'system {} upgraded'.format(submsg)
    module.exit_json(**result)


def upgrade(module, pacman, result):
    '''
    Upgrade the whole system.
    '''
    handler = get_handler(module, pacman)
    cmd = []

    if handler == pacman:
        if get_current_user_name(module) != 'root':
            result['msg'] = 'could not upgrade the system as a non-root user when no pacman\'s wrapper is installed'
            module.fail_json(**result)

        cmd = [pacman, '-S', '-u', '-q', '--noconfirm']
    else:
        cmd = get_pacman_wrapper_command(handler, True)

    rc, stdout, _ = module.run_command([handler, '-Q', '-u'])

    if rc != 0 or not stdout:
        result['msg'] = 'system is up to date'
        module.exit_json(**result)

    cmd.extend(split_extra_args(module.params['extra_args']))
    rc, _, stderr = module.run_command(cmd, check_rc=False)

    if rc != 0:
        result['msg'] = 'could not upgrade the system: {}'.format(stderr)
        module.fail_json(**result)

    result['handler'] = handler
    return_upgrade_result(module, 'has been', result)


def is_local_package(package):
    '''
    Determine if the package is a filename of the local package file.
    '''
    return re.match(r'^.+\.pkg\.tar(\.(gz|bz2|xz|lrz|lzo|Z))?$', package)


def get_aur_package_info(package):
    '''
    Retrieve information about the AUR package.
    '''
    url = 'https://aur.archlinux.org/rpc/?v=5&type=info&arg={}'.format(urllib.parse.quote(package))
    request_result = open_url(url)
    return json.loads(request_result.read().decode('utf8'))


def is_aur_package(package):
    '''
    Determine if the package is available in the AUR.
    '''
    info = get_aur_package_info(package)
    return info['resultcount'] > 0


def is_official_package(module, package, pacman):
    '''
    Determine if the package is available in the official repositories.
    '''
    ere = '^{}$'.format(package)
    rc, _, _ = module.run_command([pacman, '-S', '-s', ere], check_rc=False)
    return rc == 0


def extract_packages(module, package_group, pacman):
    '''
    Extract the package list from the official repository package group.
    '''
    packages = []
    rc, stdout, _ = module.run_command([pacman, '-S', '-g', '-q', package_group], check_rc=False)

    if rc == 0:
        for item in stdout.split('\n'):
            item = item.strip()

            if item:
                packages.append(item)

    return packages


def group_packages(module, names, pacman, result):
    '''
    Group packages by their origin.
    '''
    packages = []
    aur_packages = []
    local_packages = []

    if module.params['state'] != 'absent':
        for name in names:
            if name:
                if is_local_package(name):
                    local_packages.append(name)
                elif is_aur_package(name) and not module.params['force']:
                    aur_packages.append(name)
                elif is_official_package(module, name, pacman):
                    extracted = extract_packages(module, name, pacman)
                    packages.extend(extracted) if extracted else packages.append(name)
                else:
                    result['msg'] = 'unavailable package has been detected'
                    module.fail_json(**result)
    else:
        packages = list(filter(None, names))

    return (packages, aur_packages, local_packages)


def is_package_installed(module, package, pacman):
    '''
    Determine if the package is already installed.
    '''
    rc, _, _ = module.run_command([pacman, '-Q', package], check_rc=False)
    return rc == 0


def get_package_version(module, package, pacman, remote_version=False):
    '''
    Retrieve version of the package that has been already installed or remote package version from the official
    repositories.
    '''
    query_parameter = '-S' if remote_version else '-Q'
    rc, stdout, _ = module.run_command([pacman, query_parameter, '-i', package], check_rc=False)
    version = None

    if rc == 0:
        version_line = 2 if remote_version else 1
        line = stdout.split('\n')[version_line]
        version = line.split(':')[-1].strip()

    return version


def get_aur_package_version(package):
    '''
    Retrieve version of the package from the AUR.
    '''
    info = get_aur_package_info(package)
    version = None

    if info['resultcount'] > 0:
        version = info['results'][0]['Version'].split(':')[-1].strip()

    return version


def get_package_details(module, package, pacman, aur_package=False):
    '''
    Retrieve information if the package is already installed and has the latest version.
    '''
    installed = is_package_installed(module, package, pacman)
    details = {
        'package': package,
        'installed': installed,
        'latest': installed
    }

    if module.params['state'] == 'latest' and installed:
        version = get_package_version(module, package, pacman)
        remote_version = get_aur_package_version(package) if aur_package \
            else get_package_version(module, package, pacman, True)

        if remote_version is not None:
            details['latest'] = version == remote_version

    return details


def is_state_change_required(state, details):
    '''
    Check if the package state needs to be changed.
    '''
    state_change = False

    if state == 'absent' and details['installed']:
        state_change = True

    if state == 'present' and not details['installed']:
        state_change = True

    if state == 'latest' and not (details['installed'] and details['latest']):
        state_change = True

    return state_change


def return_name_result(module, number_of_changes, single_package, result, check_mode=False):
    '''
    Prepare and return result for the name option.
    '''
    state = module.params['state']
    multiple_submsg = 'would be' if check_mode else 'have been'
    single_submsg = 'would be' if check_mode else 'has been'

    if number_of_changes > 0:
        result['changed'] = True
        result['msg'] = '{} packages {} {}'.format(number_of_changes, multiple_submsg, state_equivalents[state]) \
            if number_of_changes > 1 else 'package {} {}'.format(single_submsg, state_equivalents[state])
    else:
        result['msg'] = 'package is already {}'.format(state_equivalents[state]) if single_package \
            else 'all packages are already {}'.format(state_equivalents[state])

    module.exit_json(**result)


def run_name_check_mode(module, packages, aur_packages, local_packages, pacman, result):
    '''
    Inform the user what would change if the module were run with the name option.
    '''
    state = module.params['state']
    collected_details = []
    number_of_changes = 0

    for package in packages:
        collected_details.append(get_package_details(module, package, pacman))

    if state != 'absent':
        for package in aur_packages:
            collected_details.append(get_package_details(module, package, pacman, True))

        for package in local_packages:
            package = re.sub(package_version_pattern, '', package.split('/')[-1])
            collected_details.append(get_package_details(module, package, pacman))

    for details in collected_details:
        if is_state_change_required(state, details):
            number_of_changes += 1

    return_name_result(module, number_of_changes, len(collected_details) == 1, result, True)


def prepare_remove_package_command(module, pacman):
    '''
    Prepare and return the remove package command.
    '''
    params = module.params
    cmd = [pacman, '-R']

    if params['force']:
        cmd.extend(['-d', '-d'])

    cmd.extend(['--noconfirm', '--noprogressbar'])
    cmd.extend(split_extra_args(params['extra_args']))
    return cmd


def remove_packages(module, packages, pacman, result):
    '''
    Uninstall the desired package(s).
    '''
    number_of_changes = 0

    for package in packages:
        package_details = get_package_details(module, package, pacman)

        if package_details['installed']:
            cmd = prepare_remove_package_command(module, pacman)
            cmd.append(package_details['package'])
            rc, _, stderr = module.run_command(cmd, check_rc=False)

            if rc != 0:
                result['msg'] = 'failed to remove {}: {}'.format(package_details['package'], stderr)
                module.fail_json(**result)

            number_of_changes += 1

    return_name_result(module, number_of_changes, len(packages) == 1, result)


def run_install_packages_command(module, cmd, packages, result):
    '''
    Execute the install package(s) command.
    '''
    cmd.extend(split_extra_args(module.params['extra_args']))
    cmd.extend(packages)
    rc, _, stderr = module.run_command(cmd, check_rc=False)

    if rc != 0:
        result['msg'] = 'failed to install {}: {}'.format(' '.join(packages), stderr)
        module.fail_json(**result)


def install_packages_with_pacman(module, packages, pacman, result, local_resources=False):
    '''
    Install the desired package(s) with using pacman.
    '''
    packages_to_install = []

    for package in packages:
        package_name = re.sub(package_version_pattern, '', package.split('/')[-1]) if local_resources else package

        if is_state_change_required(module.params['state'], get_package_details(module, package_name, pacman)):
            packages_to_install.append(package)

    if packages_to_install:
        cmd = [pacman, '-U'] if local_resources else [pacman, '-S']
        cmd.extend(['--needed', '--noconfirm', '--noprogressbar'])
        run_install_packages_command(module, cmd, packages_to_install, result)

    return len(packages_to_install)


def install_packages_with_wrapper(module, packages, aur_packages, wrapper, pacman, result):
    '''
    Install the desired package(s) with using the pacman's wrapper.
    '''
    params = module.params
    packages_to_install = []

    for package in packages:
        if is_state_change_required(params['state'], get_package_details(module, package, pacman)):
            packages_to_install.append(package)

    for package in aur_packages:
        if is_state_change_required(params['state'], get_package_details(module, package, pacman, True)):
            packages_to_install.append(package)

    if packages_to_install:
        run_install_packages_command(module, get_pacman_wrapper_command(wrapper), packages_to_install, result)

    return len(packages_to_install)


def download_aur_package(file_name, url_path):
    '''
    Download package from the AUR.
    '''
    file_url = open_url('https://aur.archlinux.org/{}'.format(url_path))

    with open(file_name, 'wb') as stream:
        stream.write(file_url.read())


def extract_tar_file(file_name):
    '''
    Extract package from the tar file.
    '''
    tar = tarfile.open(file_name)
    tar.extractall()
    tar.close()


def prepare_aur_package_install_command(module):
    '''
    Prepare and return the package install command with using makepkg.
    '''
    cmd = [module.get_bin_path('makepkg'), '-s', '-i', '--needed', '--noconfirm', '--noprogressbar']
    cmd.extend(split_extra_args(module.params['extra_args']))
    return cmd


def install_aur_packages_with_makepkg(module, packages, pacman, result):
    '''
    Install the desired AUR package(s) with using makepkg.
    '''
    params = module.params
    cmd = prepare_aur_package_install_command(module)
    current_directory = os.getcwd()
    number_of_changes = 0

    for package in packages:
        if is_state_change_required(params['state'], get_package_details(module, package, pacman, True)):
            info = get_aur_package_info(package)

            if info['resultcount'] < 1:
                result['msg'] = 'failed to install {}: could not retrieve the package details'.format(package)
                module.fail_json(**result)

            package_name = info['results'][0]['Name'].strip()
            url_path = info['results'][0]['URLPath'].strip()
            tar_file_name = '{}.tar.gz'.format(package_name)

            with tempfile.TemporaryDirectory() as temporary_directory:
                os.chdir(temporary_directory)
                download_aur_package(tar_file_name, url_path)
                extract_tar_file(tar_file_name)
                os.chdir(package_name)
                rc, _, stderr = module.run_command(cmd, check_rc=True)

                if rc != 0:
                    result['msg'] = 'failed to install {}: {}'.format(package, stderr)
                    module.fail_json(**result)

                number_of_changes += 1

    os.chdir(current_directory)
    return number_of_changes


def install_packages_with_aur_support(module, packages, aur_packages, pacman, result):
    '''
    Install the desired package(s) with the AUR support.
    '''
    if get_current_user_name(module) == 'root':
        result['msg'] = 'could not install aur packages as a root'
        module.fail_json(**result)

    handler = get_handler(module, pacman)
    number_of_changes = 0

    if handler != pacman:
        number_of_changes = install_packages_with_wrapper(module, packages, aur_packages, handler, pacman, result)
    else:
        if packages:
            result['msg'] = 'could not install packages from the official repositories mixed with aur packages when ' \
                'no pacman\'s wrapper is installed'
            module.fail_json(**result)

        module.get_bin_path('fakeroot', True)
        number_of_changes = install_aur_packages_with_makepkg(module, aur_packages, pacman, result)
        handler = module.get_bin_path('makepkg')

    return (handler, number_of_changes)


def install_packages(module, packages, aur_packages, local_packages, pacman, result):
    '''
    Install the desired package(s).
    '''
    handler = pacman
    number_of_all_packages = len(packages) + len(aur_packages) + len(local_packages)
    number_of_changes = 0

    if aur_packages:
        handler, number_of_changes = install_packages_with_aur_support(module, packages, aur_packages, pacman, result)
    else:
        if get_current_user_name(module) != 'root':
            result['msg'] = 'could not install neither packages from the official repositories nor local packages ' \
                'as a non-root user'
            module.fail_json(**result)

        if packages:
            number_of_changes = install_packages_with_pacman(module, packages, pacman, result)

        if local_packages:
            number_of_changes += install_packages_with_pacman(module, local_packages, pacman, result, True)

    result['handler'] = handler
    return_name_result(module, number_of_changes, number_of_all_packages == 1, result)


def run_module():
    module_args = dict(
        name=dict(type='list', elements='str', aliases=['package', 'pkg']),
        state=dict(type='str', default='present', choices=['absent', 'latest', 'present']),
        upgrade=dict(type='bool', default=False),
        update_cache=dict(type='bool', default=False, aliases=['update-cache']),
        force=dict(type='bool', default=False),
        extra_args=dict(type='str', default='')
    )

    result = dict(
        changed=False,
        msg='no action has been taken',
        handler=None
    )

    module = AnsibleModule(
        argument_spec=module_args,
        required_one_of=[['name', 'upgrade', 'update_cache']],
        mutually_exclusive=[['name', 'upgrade']],
        supports_check_mode=True
    )

    pacman = module.get_bin_path('pacman', True)
    params = module.params

    if params['update_cache']:
        if not module.check_mode:
            refresh_package_databases(module, pacman, result)

            if not (params['name'] or params['upgrade']):
                return_update_cache_result(module, 'have been', result)
        elif not (params['name'] or params['upgrade']):
            return_update_cache_result(module, 'would be', result)

    if params['upgrade']:
        if module.check_mode:
            return_upgrade_result(module, 'would be', result)
        else:
            upgrade(module, pacman, result)

    if params['name']:
        packages, aur_packages, local_packages = group_packages(module, params['name'], pacman, result)

        if aur_packages and local_packages:
            result['msg'] = 'could not install aur packages mixed with local packages'
            module.fail_json(**result)

        if module.check_mode:
            run_name_check_mode(module, packages, aur_packages, local_packages, pacman, result)

        if params['state'] == 'absent':
            remove_packages(module, packages, pacman, result)
        else:
            install_packages(module, packages, aur_packages, local_packages, pacman, result)
    else:
        module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
