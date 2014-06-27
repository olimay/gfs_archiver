#!/usr/env python

import sys
import os
import time
import codecs
import datetime
from slacker import Slacker
from json import loads
from sys import argv
from config import API_TOKEN, _BASE_PATH

# make sure this gets reset every time you use a new Slacker object
ACTIVE_USER_INFO = None 

MEMBERS_BY_ID = None
ATTEMPT_LIMIT = 300

_SUBDIRS = {
    "PM_SUBDIR" : "private_messages",
    "GROUPS_SUBDIR" : "groups",
    "FILES_SUBDIR" : "files",
    "FAV_SUBDIR" : "favorites"
}

def _set_active_user_info(slack):
    global ACTIVE_USER_INFO
    response = None
    attempts = 0
    while not response and attempts < ATTEMPT_LIMIT:
        response = slack.auth.test()
        attempts += 1
    if response:
        if response.body["ok"]:
            ACTIVE_USER_INFO = response.body
            print ACTIVE_USER_INFO
            return
        elif "error" in response.body.keys():
            print "API error (auth.test) : %s" % (
                response.body["error"],
            )
        else:
            print "API error (auth.test) : unknown error"
            exit(1)
    else:
        print "API request (auth.test) failed after %d attempts; giving up" % attempts
        exit(1)

def my_user_id(slack):
    global ACTIVE_USER_INFO
    if slack:
        if not ACTIVE_USER_INFO:
            _set_active_user_info(slack)            
        if ACTIVE_USER_INFO:
            return ACTIVE_USER_INFO["user_id"]
    return None

def my_user_name(slack):
    global ACTIVE_USER_INFO
    if slack:
        if not ACTIVE_USER_INFO:
            _set_active_user_info(slack)            
        if ACTIVE_USER_INFO:
            return ACTIVE_USER_INFO["user"]
    return None

def members_by_id(slack):
    global MEMBERS_BY_ID
    if slack:
        if not MEMBERS_BY_ID:
            response_user_list = slack.users.list()
            ulist_ok = response_user_list.body["ok"]
            if not ulist_ok:
                print "There was an error fetching the user list..."
                return None
            all_members = response_user_list.body["members"]
            MEMBERS_BY_ID = dict()
            for member in all_members:
                MEMBERS_BY_ID[member["id"]] = member

        return MEMBERS_BY_ID
    return None

def member_name(userid, slack):
    if slack:
        if "USLACKBOT" == userid:
            return "Slackbot"
        elif userid in members_by_id(slack).keys():
            member = members_by_id(slack)[userid]
            return member["name"]
    return None

def groups_subdir(slack):
    global _SUBDIRS
    return user_path(slack) + os.path.sep + _SUBDIRS['PM_SUBDIR']

def favorites_subdir(slack):
    global _SUBDIRS
    return user_path(slack) + os.path.sep + _SUBDIRS['FAV_SUBDIR']

def files_subdir(slack):
    global _SUBDIRS
    return user_path(slack) + os.path.sep + _SUBDIRS['FILES_SUBDIR']

def pm_subdir(slack):
    global _SUBDIRS
    return user_path(slack) + os.path.sep + _SUBDIRS['PM_SUBDIR']
   
def user_path(slack):
    global _BASE_PATH
    if not slack:
        print "Undefined Slack Object!"
        exit(1)
    return os.path.normpath(_BASE_PATH + os.path.sep + my_user_id(slack))

def create_user_dir(slack):
    if not os.path.exists(user_path(slack)):
        os.makedirs(user_path(slack))
    all_subdirs = (
        groups_subdir(slack),
        favorites_subdir(slack),
        files_subdir(slack),
        pm_subdir(slack),
        )
    for subdir in all_subdirs:
        if not os.path.exists(subdir):
            os.makedirs(subdir)
    open(user_path(slack) + os.path.sep + my_user_name(slack), 'w').close()

def save_groups_channel(channel_id, outpath, slack, earliest_ts=0):
        if not slack:
            print "Undefined slack object! Aborting PM channel archive."
            return -1

        outfile = open(outpath, 'w')
        attempts = 0
        message_count = -1

        groups_history_has_more = True 
        ts_next = time.time()
        while groups_history_has_more:

            response_groups_history = None
            while not response_groups_history and attempts < ATTEMPT_LIMIT:
                response_groups_history = slack.groups.history(channel_id, ts_next, earliest_ts)                
                attempts += 1
                if (attempts % 50) == 0:
                    print "...%d attempts on %s..." % (attempts, channel_id,)

            if not response_groups_history:
                print "Could not access Slack API for groups.history after %d attempts." % (attempts,)
                if -1 == message_count:
                    return message_count

            if not response_groups_history.body["ok"]:
                error_code = response_groups_history.body["error"]
                if error_code:
                    print "Request groups.history returned error: %s" % (error_code,)
                else:
                    print "Request groups.history returned unknown error."
                if -1 == message_count:
                    return message_count

            groups_history_messages = response_groups_history.body["messages"]
            outfile.write("messages = [\n")
            for groups_message in groups_history_messages:
                if 0 >= message_count:
                    msg = unicode(groups_message)
                    outfile.write(msg)
                else:
                    msg =  u",\n%s" % (groups_message,)
                    outfile.write(msg)
                ts_next = groups_message["ts"]
                message_count += 1
            
            if -1 == message_count:
                message_count = 0

            message_count += len(groups_history_messages)
            groups_history_has_more = response_groups_history.body["has_more"]

        outfile.write("\n]\n")
        outfile.close()

        return message_count

def save_groups(slack, earliest_ts=0):

    """
    for userid in members_by_id(slack).keys():
        print "%s : %s" % (userid, member_name(userid, slack),)
    """

    response_groups_list = slack.groups.list()
    status_ok = response_groups_list.body["ok"]
    if not status_ok:
        print "Error getting groups."
        return 1

    groups_list = response_groups_list.body["groups"]

    # print groups_list
    for groups_channel in groups_list:
        group_name = groups_channel["name"]
        channel_id = groups_channel["id"]
        ts = datetime.datetime.fromtimestamp(
              time.time()
            ).strftime('%Y-%m-%d_%H%M_%S')

        filename = "%s_%s_%s.json" % (group_name, channel_id, ts,) 
        filepath = groups_subdir(slack) + os.path.sep + filename
        count = save_groups_channel(channel_id, filepath, slack)
        if 0 > count:
            print "Could not get messages for %s (%s)." % (group_name, channel_id,)
        else:
            print "%s (%s) : %d messages saved" % (group_name, channel_id, count, )


def save_pms_channel(channel_id, outpath, slack, earliest_ts=0):
        if not slack:
            print "Undefined slack object! Aborting PM channel archive."
            return -1

        outfile = open(outpath, 'w')
        attempts = 0
        message_count = -1

        im_history_has_more = True 
        ts_next = time.time()
        while im_history_has_more:

            response_im_history = None
            while not response_im_history and attempts < ATTEMPT_LIMIT:
                response_im_history = slack.im.history(channel_id, ts_next, earliest_ts)                
                attempts += 1
                if (attempts % 50) == 0:
                    print "...%d attempts on %s..." % (attempts, channel_id,)

            if not response_im_history:
                print "Could not access Slack API for im.history after %d attempts." % (attempts,)
                if -1 == message_count:
                    return message_count

            if not response_im_history.body["ok"]:
                error_code = response_im_history.body["error"]
                if error_code:
                    print "Request im.history returned error: %s" % (error_code,)
                else:
                    print "Request im.history returned unknown error."
                if -1 == message_count:
                    return message_count

            im_history_messages = response_im_history.body["messages"]
            outfile.write("messages = [\n")
            for im_message in im_history_messages:
                if 0 >= message_count:
                    msg = unicode(im_message)
                    outfile.write(msg)
                else:
                    msg =  u",\n%s" % (im_message,)
                    outfile.write(msg)
                ts_next = im_message["ts"]
                message_count += 1
            
            if -1 == message_count:
                message_count = 0

            message_count += len(im_history_messages)
            im_history_has_more = response_im_history.body["has_more"]

        outfile.write("\n]\n")
        outfile.close()

        return message_count

def save_pms(slack, earliest_ts=0):
    response_im_list = slack.im.list()
    status_ok = response_im_list.body["ok"]
    if not status_ok:
        print "Error getting IM channels."
        return 1

    im_list = response_im_list.body["ims"]
    # print im_list
    for im_channel in im_list:
        channel_id = im_channel["id"]
        user_id = im_channel["user"]
        user_name = member_name(user_id, slack)
        ts = datetime.datetime.fromtimestamp(
              time.time()
            ).strftime('%Y-%m-%d_%H%M_%S')

        filename = "%s_%s_%s.json" % (user_name, user_id, ts,) 
        filepath = pm_subdir(slack) + os.path.sep + filename
        count = save_pms_channel(channel_id, filepath, slack)
        if 0 > count:
            print "Could not get messages with %s (%s)." % (user_name, user_id,)
        else:
            print "%s (%s) : %d messages saved" % (user_name, user_id, count, )

def save_user_data(api_token):
    slack = Slacker(api_token)
    create_user_dir(slack)
    save_pms(slack)
    save_groups(slack)

def reset_active_user():
    global ACTIVE_USER_INFO
    ACTIVE_USER_INFO = None

def main(*args):
    UTF8Writer = codecs.getwriter('utf8')
    sys.stdout = UTF8Writer(sys.stdout)
    print "Arching data for %d users " % len(API_TOKEN)
    for username in API_TOKEN.keys():
        print "=== %s ===" % (username,)
        save_user_data(API_TOKEN[username])
        reset_active_user()

if __name__ == "__main__":
    success = main(argv)
    exit(success)

