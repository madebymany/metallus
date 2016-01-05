# coding: utf-8

from __future__ import print_function
import slack
import slack.chat
import slack.users
from slack.exception import ChannelArchivedError

SLACK_ICON_URL = "https://s3-eu-west-1.amazonaws.com/metallus/metallus_72.jpg"


class NotifierNotConfiguredError(Exception):
    pass


class NotificationManager(object):

    def __init__(self, config):
        self.config = config
        self.notifiers = {}
        for k, v in self.config.iteritems():
            try:
                self.notifiers[k] = self._get_notifier(k, v)
            except NotifierNotConfiguredError as e:
                print("warning: skipping loading {} notifier: {}".
                      format(k, e.message))

    def run_hook(self, hook, context):
        for k, v in self.notifiers.iteritems():
            cxt = context.get(k)
            if not cxt:
                continue
            for name, value in cxt.iteritems():
                v.set_config(name, value)
            for name, value in context.iteritems():
                v.set_config(name, value)
            try:
                v.notify(hook)
            except HookNotFoundException:
                print("not running hook, not configured for {}".format(k))

    def _get_notifier(self, name, config):
        if name == "slack":
            return SlackNotifier(name, config)
        else:
            raise NotifierNotFoundException()


class SlackNotifier(object):

    def __init__(self, name, config):
        self.name = name
        self.config = config

    def set_config(self, name, value):
        self.config[name] = value

    def notify(self, hook):
        try:
            token = self.config["token"]
        except KeyError:
            raise NotifierNotConfiguredError("Slack API token not configured")
        slack.api_token = token

        if hook not in self.config["hooks"]:
            raise HookNotFoundException()
        try:
            slack.chat.post_message(self.config["channel"],
                                    self.format_message(
                                        self.config["hooks"][hook]),
                                    username="metallus",
                                    icon_url=SLACK_ICON_URL,
                                    link_names=1)
        except ChannelArchivedError as e:
            print(e)

    def format_message(self, message):
        for k, v in self.config.iteritems():
            pattern = "{" + k + "}"
            if pattern in message:
                if k == "author":
                    v = self.get_username(v)
                message = message.replace(pattern, v)
        return message

    def get_username(self, actor):
        for u in slack.users.list()["members"]:
            if "profile" in u:
                name = u.get("name").lower()
                email = u["profile"].get("email", "").lower()
                real_name = u["profile"]["real_name"].lower()

                if type(actor) is str:
                    return actor

                if name == actor.name.lower() or \
                   real_name == actor.name.lower() or \
                   email == actor.email.lower():
                    return "@" + name
        return actor.name


class HookNotFoundException(Exception):
    pass


class NotifierNotFoundException(Exception):
    pass
