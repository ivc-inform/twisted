
# System Imports
import md5
import string

# Twisted Imports
from twisted.spread import pb
from twisted.python import authenticator
from twisted import copyright

# Status "enumeration"

OFFLINE = 0
ONLINE  = 1
AWAY = 2

statuses = {
    0: "Offline",
    1: "Online",
    2: "Away"
    }

class Participant(pb.Perspective):
    def __init__(self, name, password, service):
        self.name = name
        self.service = service
        self.password = md5.new(password).digest()
        self.status = OFFLINE
        self.contacts = []
        self.reverseContacts = []
        self.groups = []
        self.client = None
        self.info = ""

    def attached(self, client):
        if self.client:
            raise authenticator.Unauthorized("duplicate login not permitted.")
        print "attached: %s" % self.name
        self.client = client
        client.receiveContactList(map(lambda contact: (contact.name, contact.status),
                                      self.contacts))
        self.changeStatus(ONLINE)

    def changeStatus(self, newStatus):
        self.status = newStatus
        for contact in self.reverseContacts:
            contact.notifyStatusChanged(self)

    def notifyStatusChanged(self, contact):
        if self.client:
            self.client.notifyStatusChanged(contact.name, contact.status)

    def detached(self, client):
        print "detached: %s" % self.name
        self.client = None
        if self.groups:
            for group in self.groups:
                group.removeMember(self)
        self.changeStatus(OFFLINE)

    def addContact(self, contactName):
        contact = self.service.getPerspectiveNamed(contactName)
        self.contacts.append(contact)
        contact.reverseContacts.append(self)
        self.notifyStatusChanged(contact)

    def removeContact(self, contactName):
        for contact in self.contacts:
            if contact.name == contactName:
                self.contacts.remove(contact)
                contact.reverseContacts.remove(self)
                return
        raise pb.Error("No such contact.")

    def joinGroup(self, name):
        group = self.service.getGroup(name)
        group.addMember(self)
        self.groups.append(group)

    def leaveGroup(self, name):
        for group in self.groups:
            if group.name == name:
                self.groups.remove(group)
                group.removeMember(self)
                return
        raise pb.Error("You're not in that group.")

    def receiveDirectMessage(self, sender, message):
        if self.client:
            self.client.receiveDirectMessage(sender.name, message)
        else:
            raise pb.Error("%s not logged in" % self.name)

    def receiveGroupMessage(self, sender, group, message):
        if sender is not self and self.client:
            self.client.receiveGroupMessage(sender.name, group.name, message)

    def memberJoined(self, member, group):
        self.client.memberJoined(member.name, group.name)

    def memberLeft(self, member, group):
        self.client.memberLeft(member.name, group.name)

    def directMessage(self, recipientName, message):
        recipient = self.service.getPerspectiveNamed(recipientName)
        recipient.receiveDirectMessage(self, message)

    def groupMessage(self, groupName, message):
        for group in self.groups:
            if group.name == groupName:
                group.sendMessage(self, message)
                return
        raise pb.Error("You're not in that group.")

    # Establish client protocol for PB.
    perspective_joinGroup = joinGroup
    perspective_directMessage = directMessage
    perspective_addContact = addContact
    perspective_removeContact = removeContact


class Group(pb.Cached):

    def __init__(self, name):
        self.name = name
        self.members = []
        self.topic = "Welcome to '%s'." % self.name

    def getStateToCopyFor(self, participant):
        assert participant in self.members, "illegal copy of group"
        return {'name':    self.name,
                'members': self.members,
                'remote':  pb.Proxy(participant, self)}

    def addMember(self, participant):
        for member in self.members:
            member.memberJoined(participant, self)
        self.members.append(participant)

    def removeMember(self, participant):
        self.members.remove(participant)
        for member in self.members:
            member.memberLeft(participant, self)

    def sendMessage(self, sender, message):
        for member in self.members:
            member.receiveGroupMessage(sender, self, message)


class Service(pb.Service):
    """I am a chat service.
    """

    def __init__(self):
        self.participants = {}
        self.groups = {}

    def getGroup(self, name):
        group = self.groups.get(name)
        if not group:
            group = Group(name)
            self.groups[name] = group
        return group

    def addParticipant(self, name, password):
        if not self.participants.has_key(name):
            print "Created New Participant: %s" % name
            p = Participant(name, password, self)
            self.participants[name] = p
            return p

    def getPassword(self, name):
        return self.getPerspectiveNamed(name).password

    def getPerspectiveNamed(self, name):
        return self.participants[name]


