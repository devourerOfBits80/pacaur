# pacaur

[Ansible](https://www.ansible.com) module to manage [Arch Linux](https://www.archlinux.org) OS packages from the official repositories and from the [AUR](https://aur.archlinux.org/).

For packages that are available in the official repositories and also for local packages, it uses the [pacman](https://wiki.archlinux.org/index.php/pacman) by default. In the case of AUR packages, it tries to find one of the predefined pacman's wrapper and use it as a package manager. Otherwise, it uses an approach with the [makepkg](https://wiki.archlinux.org/index.php/Makepkg).

The following pacman wrappers are currently supported (additional can be added):

- [yay](https://aur.archlinux.org/packages/yay/)
- [pikaur](https://aur.archlinux.org/packages/pikaur/)
- [trizen](https://aur.archlinux.org/packages/trizen/)

## Installation

Clone the *pacaur* repository into the Ansible custom modules directory at the user account:

> \$ git clone <https://github.com/devourerOfBits80/pacaur.git> ~/.ansible/plugins/modules/pacaur

Alternatively, you can just copy or link the *pacaur.py* file into the *library* directory that should be available inside the top-level of your Ansible project (for example):

> \$ git submodule add <https://github.com/devourerOfBits80/pacaur.git> ./project_directory/library/pacaur  
> \$ git submodule update --init --recursive (only for older versions of Git)

## Usage

### Options

|parameter   |default|choices                |description                                                                          |
|------------|-------|-----------------------|-------------------------------------------------------------------------------------|
|name        |       |                       |Name or name list of the package(s) to install, upgrade or remove.                   |
|state       |present|present, latest, absent|Desired state of the package(s).                                                     |
|upgrade     |no     |yes, no                |Whether or not to upgrade the whole system.                                          |
|update_cache|no     |yes, no                |Whether or not to refresh the master package databases for the official repositories.|
|force       |no     |yes, no                |Whether or not to force required action.                                             |
|extra_args  |       |                       |Additional option(s) that should be passed to the package manager.                   |

- Either the name or upgrade option is required however, they cannot be used simultaneously.
- The update-cache option can be used as a part of the name or upgrade option and also as a separate step.
- The force option has an impact on a few actions. During the package(s) installing or updating, it is responsible for enforcing the package details checking in the official repositories. During the package(s) removing, it is responsible for skipping all dependencies checking. Finally, during the cache updating, it is responsible for refreshing all package databases, even if they appear to be up-to-date.
- Some actions are only available if the pacman's wrapper eg. yay, pikaur or trizen is already installed in the system.

### Examples

```yaml
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
```
