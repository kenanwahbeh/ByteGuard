"""The setup questions: network card, public address, port and the first device."""

from dataclasses import dataclass

from byteguard import netdetect, wg
from byteguard.errors import ByteGuardError
from byteguard.prompt import Terminal

DEFAULT_PORT = 51820
DEFAULT_DEVICE = "phone"


@dataclass(frozen=True)
class Answers:
    iface: str
    endpoint: str
    port: int
    first_device: str


def gather(
    *,
    run,
    term: Terminal | None,
    iface: str | None = None,
    endpoint: str | None = None,
    port: int | None = None,
    first_device: str | None = None,
    public_address=netdetect.public_address,
    port_is_free=netdetect.port_is_free,
) -> Answers:
    """Collect the setup answers, asking on `term` for whatever was not given.

    With no terminal nothing is asked: missing answers take the detected or
    default value, and a value that cannot be detected is an error.
    """
    cards = netdetect.interfaces(run)
    if not cards:
        raise ByteGuardError("No network card with an IPv4 address was found.")

    iface = _iface(term, run, cards, iface)
    endpoint = _endpoint(term, endpoint, lambda: public_address() or cards[iface])
    port = _port(term, port, port_is_free)
    first_device = _first_device(term, first_device)

    answers = Answers(iface, endpoint, port, first_device)
    if term is not None:
        term.say()
        term.say("About to set up the VPN server with:")
        term.say(f"  Network card     {answers.iface} ({cards[answers.iface]})")
        term.say(f"  Public address   {answers.endpoint}")
        term.say(f"  WireGuard port   {answers.port}/udp")
        term.say(f"  First device     {answers.first_device}")
        if not term.confirm("Apply these settings?"):
            raise ByteGuardError("Setup cancelled. Nothing was changed.")
    return answers


def _iface(term, run, cards: dict[str, str], given: str | None) -> str:
    if given is not None:
        if given not in cards:
            raise ByteGuardError(
                f"There is no network card named {given!r} with an IPv4 address. "
                f"Available: {', '.join(cards)}."
            )
        return given
    detected = netdetect.default_interface(run)
    if detected not in cards:
        detected = None
    if term is None:
        if detected is None:
            raise ByteGuardError("Could not tell which network card faces the internet; pass --iface.")
        return detected
    if detected is not None:
        term.say(f"Internet-facing network card: {detected} ({cards[detected]})")
        if term.confirm("Is this the one to use?"):
            return detected
    names = list(cards)
    return names[term.choose("Which network card faces the internet?", [f"{n} ({cards[n]})" for n in names])]


def _endpoint(term, given: str | None, detect) -> str:
    if given is not None:
        if not netdetect.valid_endpoint(given):
            raise ByteGuardError(f"{given!r} is not an IP address or a host name.")
        return given
    detected = detect()
    if term is None:
        return detected
    while True:
        answer = term.ask("Public address devices will connect to (IP or host name)", detected)
        if netdetect.valid_endpoint(answer):
            return answer
        term.say("That is not an IP address or a host name.")


def _port_problem(port: int, port_is_free) -> str | None:
    if not 1 <= port <= 65535:
        return "The port has to be between 1 and 65535."
    if not port_is_free(port):
        return f"UDP port {port} is already in use on this server."
    return None


def _port(term, given: int | None, port_is_free) -> int:
    if given is not None or term is None:
        port = DEFAULT_PORT if given is None else given
        problem = _port_problem(port, port_is_free)
        if problem:
            raise ByteGuardError(problem)
        return port
    while True:
        answer = term.ask("WireGuard port", str(DEFAULT_PORT))
        problem = "The port has to be a number." if not answer.isdigit() else _port_problem(int(answer), port_is_free)
        if problem is None:
            return int(answer)
        term.say(problem)


def _first_device(term, given: str | None) -> str:
    if given is not None or term is None:
        name = given or DEFAULT_DEVICE
        wg.check_name(name)
        return name
    while True:
        answer = term.ask("Name for your first device", DEFAULT_DEVICE)
        try:
            wg.check_name(answer)
        except ByteGuardError as error:
            term.say(str(error))
        else:
            return answer
