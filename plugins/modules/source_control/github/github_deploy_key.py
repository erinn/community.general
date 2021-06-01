#!/usr/bin/python
# -*- coding: utf-8 -*-

# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


DOCUMENTATION = '''
---
module: github_deploy_key

author: "Ali (@bincyber)"

short_description: Manages deploy keys for GitHub repositories.

description:
  - "Adds or removes deploy keys for GitHub repositories. Supports authentication using OAuth2 token, or personal access token. Admin
  rights on the repository are required."

extends_documentation_fragment:
- community.general.github

options:
  github_url:
    description:
      - The base URL of the GitHub API
    required: false
    type: str
    version_added: '0.2.0'
    default: https://api.github.com
  owner:
    description:
      - The name of the individual account or organization that owns the GitHub repository.
    required: true
    aliases: [ 'account', 'organization' ]
    type: str
  repo:
    description:
      - The name of the GitHub repository.
    required: true
    aliases: [ 'repository' ]
    type: str
  name:
    description:
      - The name for the deploy key.
    required: true
    aliases: [ 'title', 'label' ]
    type: str
  key:
    description:
      - The SSH public key to add to the repository as a deploy key.
    required: true
    type: str
  read_only:
    description:
      - If C(true), the deploy key will only be able to read repository contents. Otherwise, the deploy key will be able to read and write.
    type: bool
    default: 'yes'
  state:
    description:
      - The state of the deploy key.
    default: "present"
    choices: [ "present", "absent" ]
    type: str
  force:
    description:
      - If C(true), forcefully adds the deploy key by deleting any existing deploy key with the same public key or title.
    type: bool
    default: 'no'
notes:
   - "Refer to GitHub's API documentation here: https://developer.github.com/v3/repos/keys/."
'''

EXAMPLES = '''
- name: Add a new read-only deploy key to a GitHub repository using basic authentication
  community.general.github_deploy_key:
    owner: "johndoe"
    repo: "example"
    name: "new-deploy-key"
    key: "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDAwXxn7kIMNWzcDfou..."
    read_only: yes
    token: "ABAQDAwXxn7kIMNWzcDfo..."

- name: Remove an existing deploy key from a GitHub repository
  community.general.github_deploy_key:
    owner: "johndoe"
    repository: "example"
    name: "new-deploy-key"
    key: "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDAwXxn7kIMNWzcDfou..."
    force: yes
    token: "ABAQDAwXxn7kIMNWzcDfo..."
    state: absent

- name: Add a new deploy key to a GitHub repository, replace an existing key, use an OAuth2 token to authenticate
  community.general.github_deploy_key:
    owner: "johndoe"
    repository: "example"
    name: "new-deploy-key"
    key: "{{ lookup('file', '~/.ssh/github.pub') }}"
    force: yes
    token: "ABAQDAwXxn7kIMNWzcDfo..."

- name: Re-add a deploy key to a GitHub repository but with a different name
  community.general.github_deploy_key:
    owner: "johndoe"
    repository: "example"
    name: "replace-deploy-key"
    key: "{{ lookup('file', '~/.ssh/github.pub') }}"
    token: "ABAQDAwXxn7kIMNWzcDfo..."

- name: Add a new deploy key to a GitHub repository using 2FA
  community.general.github_deploy_key:
    owner: "johndoe"
    repo: "example"
    name: "new-deploy-key-2"
    key: "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDAwXxn7kIMNWzcDfou..."
    token: "ABAQDAwXxn7kIMNWzcDfo..."
    otp: 123456

- name: Add a read-only deploy key to a repository hosted on GitHub Enterprise
  community.general.github_deploy_key:
    github_url: "https://api.example.com"
    owner: "janedoe"
    repo: "example"
    name: "new-deploy-key"
    key: "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDAwXxn7kIMNWzcDfou..."
    read_only: yes
    token: "ABAQDAwXxn7kIMNWzcDfo..."
'''

RETURN = '''
msg:
    description: the status message describing what occurred
    returned: always
    type: str
    sample: "Deploy key added successfully"

http_status_code:
    description: the HTTP status code returned by the GitHub API
    returned: failed
    type: int
    sample: 400

error:
    description: the error message returned by the GitHub API
    returned: failed
    type: str
    sample: "key is already in use"

id:
    description: the key identifier assigned by GitHub for the deploy key
    returned: changed
    type: int
    sample: 24381901
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import fetch_url
from re import findall


class GithubDeployKey(object):
    def __init__(self, module):
        self.module = module

        self.github_url = self.module.params['github_url']
        self.name = module.params['name']
        self.key = module.params['key']
        self.state = module.params['state']
        self.read_only = module.params.get('read_only', True)
        self.force = module.params.get('force', False)
        self.token = module.params.get('token', None)
        self.otp = module.params.get('otp', None)

    @property
    def url(self):
        owner = self.module.params['owner']
        repo = self.module.params['repo']
        return "{0}/repos/{1}/{2}/keys".format(self.github_url, owner, repo)

    @property
    def headers(self):
        if self.token is not None:
            return {"Authorization": "token {0}".format(self.token)}
        else:
            return None

    def paginate(self, url):
        while url:
            resp, info = fetch_url(self.module, url, headers=self.headers, method="GET")

            if info["status"] == 200:
                yield self.module.from_json(resp.read())

                links = {}
                for x, y in findall(r'<([^>]+)>;\s*rel="(\w+)"', info["link"]):
                    links[y] = x

                url = links.get('next')
            else:
                self.handle_error(method="GET", info=info)

    def get_existing_key(self):
        for keys in self.paginate(self.url):
            if keys:
                for i in keys:
                    existing_key_id = str(i["id"])
                    if i["key"].split() == self.key.split()[:2]:
                        return existing_key_id
                    elif i['title'] == self.name and self.force:
                        return existing_key_id
            else:
                return None

    def add_new_key(self):
        request_body = {"title": self.name, "key": self.key, "read_only": self.read_only}

        resp, info = fetch_url(self.module, self.url, data=self.module.jsonify(request_body), headers=self.headers, method="POST", timeout=30)

        status_code = info["status"]

        if status_code == 201:
            response_body = self.module.from_json(resp.read())
            key_id = response_body["id"]
            self.module.exit_json(changed=True, msg="Deploy key successfully added", id=key_id)
        elif status_code == 422:
            self.module.exit_json(changed=False, msg="Deploy key already exists")
        else:
            self.handle_error(method="POST", info=info)

    def remove_existing_key(self, key_id):
        resp, info = fetch_url(self.module, "{0}/{1}".format(self.url, key_id), headers=self.headers, method="DELETE")

        status_code = info["status"]

        if status_code == 204:
            if self.state == 'absent':
                self.module.exit_json(changed=True, msg="Deploy key successfully deleted", id=key_id)
        else:
            self.handle_error(method="DELETE", info=info, key_id=key_id)

    def handle_error(self, method, info, key_id=None):
        status_code = info['status']
        body = info.get('body')
        if body:
            err = self.module.from_json(body)['message']

        if status_code == 401:
            self.module.fail_json(msg="Failed to connect to {0} due to invalid credentials".format(self.github_url), http_status_code=status_code, error=err)
        elif status_code == 404:
            self.module.fail_json(msg="GitHub repository does not exist", http_status_code=status_code, error=err)
        else:
            if method == "GET":
                self.module.fail_json(msg="Failed to retrieve existing deploy keys", http_status_code=status_code, error=err)
            elif method == "POST":
                self.module.fail_json(msg="Failed to add deploy key", http_status_code=status_code, error=err)
            elif method == "DELETE":
                self.module.fail_json(msg="Failed to delete existing deploy key", id=key_id, http_status_code=status_code, error=err)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            github_url=dict(required=False, type='str', default="https://api.github.com"),
            owner=dict(required=True, type='str', aliases=['account', 'organization']),
            repo=dict(required=True, type='str', aliases=['repository']),
            name=dict(required=True, type='str', aliases=['title', 'label']),
            key=dict(required=True, type='str', no_log=False),
            read_only=dict(required=False, type='bool', default=True),
            state=dict(default='present', choices=['present', 'absent']),
            force=dict(required=False, type='bool', default=False),
            token=dict(required=True, type='str', no_log=True)
        ),
        supports_check_mode=True,
    )

    deploy_key = GithubDeployKey(module)

    if module.check_mode:
        key_id = deploy_key.get_existing_key()
        if deploy_key.state == "present" and key_id is None:
            module.exit_json(changed=True)
        elif deploy_key.state == "present" and key_id is not None:
            module.exit_json(changed=False)

    # to forcefully modify an existing key, the existing key must be deleted first
    if deploy_key.state == 'absent' or deploy_key.force:
        key_id = deploy_key.get_existing_key()

        if key_id is not None:
            deploy_key.remove_existing_key(key_id)
        elif deploy_key.state == 'absent':
            module.exit_json(changed=False, msg="Deploy key does not exist")

    if deploy_key.state == "present":
        deploy_key.add_new_key()


if __name__ == '__main__':
    main()
