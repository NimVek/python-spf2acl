import abc
import enum
import logging
import re

import netaddr


__logger__ = logging.getLogger(__name__)

__all__ = [
    "SPF",
    "Qualifier",
    "Directive",
    "Mechanism",
    "All",
    "Include",
    "Exists",
    "A",
    "MX",
    "IPNetwork",
    "Macro",
    "Domain",
    "Modifier",
    "Redirect",
    "Exp",
]


class __Sequence:
    def __init__(self, data):
        self.__data = list(data)

    @property
    def data(self):
        return self.__data

    def __repr__(self):
        return (
            "%s([" % self.__class__.__name__
            + ", ".join([repr(x) for x in self.data])
            + "])"
        )


class SPF(__Sequence):
    @property
    def terms(self):
        return self.data

    @property
    def version(self):
        return "spf1"

    def __str__(self):
        result = "v=%s" % self.version
        if self.terms:
            result += " " + " ".join([str(x) for x in self.terms])
        return result


class Qualifier(str, enum.Enum):
    PASS = "+"
    FAIL = "-"
    NEUTRAL = "?"
    SOFT_FAIL = "~"


class Directive:
    def __init__(self, mechanism, qualifier=Qualifier.PASS):
        self.__mechanism = mechanism
        self.__qualifier = Qualifier(qualifier)

    @property
    def mechanism(self):
        return self.__mechanism

    @property
    def qualifier(self):
        return self.__qualifier

    def __str__(self):
        result = self.qualifier if self.qualifier != Qualifier.PASS else ""
        return result + str(self.mechanism)

    def __repr__(self):
        kwargs = ""
        if self.qualifier != Qualifier.PASS:
            kwargs += ", qualifier = %s" % self.qualifier
        return "%s(%r%s)" % (self.__class__.__name__, self.mechanism, kwargs)


class Mechanism(abc.ABC):
    @abc.abstractmethod
    def __str__(self):
        raise NotImplementedError

    @abc.abstractmethod
    def __repr__(self):
        raise NotImplementedError


class All(Mechanism):
    def __str__(self):
        return "all"

    def __repr__(self):
        return "%s()" % (self.__class__.__name__)


class __DomainMechanism(Mechanism):
    def __init__(self, domain):
        self.__domain = domain

    @property
    def domain(self):
        return self.__domain

    def _str(self):
        return ":%s" % self.domain

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.domain)


class Include(__DomainMechanism):
    def __str__(self):
        return "include" + self._str()


class Exists(__DomainMechanism):
    def __str__(self):
        return "exists" + self._str()


class __Cidr(Mechanism):
    def __init__(self, domain=None, ipv4_prefix_length=32, ipv6_prefix_length=128):
        self.__domain = domain
        self.__ipv4_prefix_length = ipv4_prefix_length
        self.__ipv6_prefix_length = ipv6_prefix_length

    @property
    def domain(self):
        return self.__domain

    @property
    def ipv4_prefix_length(self):
        return self.__ipv4_prefix_length

    @property
    def ipv6_prefix_length(self):
        return self.__ipv6_prefix_length

    def _str(self):
        result = ""
        if self.domain:
            result += ":%s" % self.domain
        if self.ipv4_prefix_length != 32:
            result += "/%d" % self.ipv4_prefix_length
        if self.ipv6_prefix_length != 128:
            result += "//%d" % self.ipv6_prefix_length
        return result

    def __repr__(self):
        kwargs = []
        if self.domain:
            kwargs.append("domain = %r" % self.domain)
        if self.ipv4_prefix_length != 32:
            kwargs.append("ipv4_prefix_length = %r" % self.ipv4_prefix_length)
        if self.ipv6_prefix_length != 128:
            kwargs.append("ipv6_prefix_length = %r" % self.ipv6_prefix_length)
        return "%s(%s)" % (self.__class__.__name__, ", ".join(kwargs))


class A(__Cidr):
    def __str__(self):
        return "a" + self._str()


class MX(__Cidr):
    def __str__(self):
        return "mx" + self._str()


class IPNetwork(Mechanism):
    def __init__(self, network):
        self.__network = netaddr.IPNetwork(network)

    @property
    def network(self):
        return self.__network.cidr

    @property
    def version(self):
        return self.network.version

    @property
    def address(self):
        return self.network.ip

    @property
    def prefix_length(self):
        return self.network.prefixlen

    def __str__(self):
        suffix = (
            "/%d" % self.prefix_length
            if self.prefix_length != self.address.netmask_bits()
            else ""
        )
        return "ip%d:%s%s" % (self.version, self.address, suffix)

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, str(self.network))


class Macro:
    class Type(str, enum.Enum):
        SENDER = "s"
        SENDER_LOCAL = "l"
        SENDER_DOMAIN = "o"
        DOMAIN = "d"
        IP = "i"
        IP_DOMAIN = "p"
        IP_VERSION = "v"
        HELO = "h"

    def __init__(self, _type, length=None, reverse=False, delimiter="."):
        self.__type = Macro.Type(_type)
        self.__length = length
        self.__reverse = reverse
        self.__delimiter = delimiter or "."

    @property
    def type(self):
        return self.__type

    @property
    def length(self):
        return self.__length

    @property
    def reverse(self):
        return self.__reverse

    @property
    def delimiter(self):
        return self.__delimiter

    def __str__(self):
        result = self.type.value
        if self.length:
            result += "%d" % self.length
        if self.reverse:
            result += "r"
        if self.delimiter != ".":
            result += self.delimiter
        return "%%{%s}" % result

    def __repr__(self):
        kwargs = ""
        if self.length:
            kwargs += ", length = %r" % self.length
        if self.reverse:
            kwargs += ", reverse = %r" % self.reverse
        if self.delimiter != ".":
            kwargs += ", delimiter = %r" % self.delimiter
        return "%s(%s%s)" % (self.__class__.__name__, self.type, kwargs)

    def expand(self, query):
        result = None
        if self.type == Macro.Type.SENDER:
            result = query.sender
        elif self.type == Macro.Type.SENDER_LOCAL:
            result = query.sender.split("@")[0]
        elif self.type == Macro.Type.SENDER_DOMAIN:
            result = query.sender.split("@")[1]
        elif self.type == Macro.Type.DOMAIN:
            result = query.domain
        elif self.type == Macro.Type.DOMAIN:
            result = query.domain
        elif self.type == Macro.Type.IP:
            if query.ip.version == 6:
                result = ".".join(
                    query.ip.format(netaddr.ipv6_verbose).replace(":", "")
                )
            else:
                result = str(query.ip)
        elif self.type == Macro.Type.IP_VERSION:
            if query.ip.version == 6:
                result = "ip6"
            else:
                result = "in-addr"
        result = re.split("|".join(map(re.escape, self.delimiter)), result)
        if self.reverse:
            result.reverse()
        if self.length:
            result = result[-self.length :]
        return ".".join(result)


class Domain(__Sequence):
    def __str__(self):
        result = ""
        for i in self.data:
            if isinstance(i, str):
                result += i.replace("%", "%%").replace("%%20", "%-").replace(" ", "%_")
            else:
                result += str(i)
        return result

    def expand(self, query):
        result = ""
        for i in self.data:
            if isinstance(i, str):
                result += i
            else:
                result += i.expand(query)
        while len(result) > 253:
            result = result[result.index(".") + 1 :]
        return result


class Modifier(abc.ABC):
    def __init__(self, domain):
        self.__domain = domain

    @property
    def domain(self):
        return self.__domain

    @abc.abstractmethod
    def __str__(self):
        raise NotImplementedError

    def _str(self):
        return "=%s" % self.domain

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.domain)


class Redirect(Modifier):
    def __str__(self):
        return "redirect" + self._str()


class Exp(Modifier):
    def __str__(self):
        return "exp" + self._str()


class Query:
    def __init__(self, sender, domain=None, ip=netaddr.IPAddress("127.0.0.1")):
        self.__sender = sender
        self.__domain = domain
        self.__ip = netaddr.IPAddress(ip)

    @property
    def sender(self):
        result = self.__sender
        if "@" not in result:
            result = "postmaster@" + result
        return result

    @property
    def domain(self):
        return self.__domain or self.sender.split("@")[1]

    @property
    def ip(self):
        return self.__ip
