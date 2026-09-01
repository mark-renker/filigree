# strudel_input_output
Source: https://strudel.cc/learn/input-output/
Fetched: 2026-08-30

# MIDI, OSC and MQTT

Normally, Strudel is used to pattern sound, using its own ‘web audio’-based synthesiser called SuperDough.

It is also possible to pattern other things with Strudel, such as software and hardware synthesisers with MIDI, other software using Open Sound Control/OSC (including the SuperDirt synthesiser commonly used with Strudel’s sibling TidalCycles), or the MQTT ‘internet of things’ protocol.

# MIDI

Strudel supports MIDI without any additional software (thanks to webmidi), just by adding methods to your pattern:

## midin(inputName?)

MIDI input: Opens a MIDI input port to receive MIDI control change messages.

The output is a function that accepts a midi cc value to query as well as (optionally) a midi channel

- input (string|number): MIDI device name or index defaulting to 0

> const cc = await midin('IAC Driver Bus 1') note("c a f e").lpf(cc(0).range(0, 1000)).lpq(cc(1).range(0, 10)).sound("sawtooth")
> const allCC = await midin('IAC Driver Bus 1') const cc = (ccNum) => allCC(ccNum, 2) // just channel 2 note("c a f e").s("saw") .when(cc(0).gt(0), x => x.postgain(0))

## midikeys(inputName?)

MIDI keyboard: Opens a MIDI input port to receive MIDI keyboard messages.

The note length is fixed as Superdough is not currently set up for undetermined note durations

The 'midichan' control value contains the number of the channel the note is coming from so it could be filtered or manipulated further in the chain.

- input (string|number): MIDI device name or index defaulting to 0

> const kb = await midikeys('Arturia KeyStep 32') kb().s("tri").lpf(80).lpe(6).lpd(0.1).room(2).delay(0.35)
> const kb = await midikeys('Arturia KeyStep 32') kb("0.5 1") .s("saw") .add(note(rand.mul(0.3))) .lpf(1000).lpe(2).room(0.5)
> // discard all notes not coming out from midi channel 2 const kb = await midikeys('Arturia KeyStep 32') kb().filterValues(v=>v.midichan==2).s("tri")

## midi(outputName?,options?)

Either connect a midi device or use the IAC Driver (Mac) or Midi Through Port (Linux) for internal midi messages. If no outputName is given, it uses the first midi output it finds.

> $: chord("<C^7 A7 Dm7 G7>").voicing().midi('IAC Driver')

In the console, you will see a log of the available MIDI devices as soon as you run the code, e.g.

```
 `Midi connected! Using "Midi Through Port-0".`
```

The

```
.midi()
```
function accepts an options object with the following properties:
> $: note("d e c a f").midi('IAC Driver', { isController: true, midimap: 'default'})

## Available Options
|Option|Type|Default|Description|
|--|--|--|--|
|isController|boolean|false|When true, disables sending note messages. Useful for MIDI controllers|
|latencyMs|number|34|Latency in milliseconds to align MIDI with audio engine|
|noteOffsetMs|number|10|Offset in milliseconds for note-off messages to prevent glitching|
|midichannel|number|1|Default MIDI channel (1-16)|
|velocity|number|0.9|Default note velocity (0-1)|
|gain|number|1|Default gain multiplier for velocity (0-1)|
|midimap|string|’default’|Name of MIDI mapping to use for control changes|
|midiport|string/number|-|MIDI device name or index|

### midiport(outputName)

Selects the MIDI output device to use, pattern can be used to switch between devices.

```
$: midiport('IAC Driver');
$: note('c a f e').midiport('<0 1 2 3>').midi();
```

MIDI port: Sets the MIDI port for the event.

- port (number|Pattern): MIDI port

> note("c a f e").midiport("<0 1 2 3>").midi()

## midichan(number)

Selects the MIDI channel to use. If not used,

```
.midi
```
will use channel 1 by default.

## midicmd(command)

```
midicmd
```
sends MIDI system real-time messages to control timing and transport on MIDI devices.
It supports the following commands:

- ```
 clock
 ```
 /
 ```
 midiClock
 ```
 - Sends MIDI timing clock messages
- ```
 start
 ```
 - Sends MIDI start message
- ```
 stop
 ```
 - Sends MIDI stop message
- ```
 continue
 ```
 - Sends MIDI continue message

// You can control the clock with a pattern and ensure it starts in sync when the repl begins. // Note: It might act unexpectedly if MIDI isn’t set up initially.

> $:stack( midicmd("clock*48,<start stop>/2").midi('IAC Driver') )

## control, ccn && ccv
- ```
 control
 ```
 sends MIDI control change messages to your MIDI device.
- ```
 ccn
 ```
 sets the cc number. Depends on your synths midi mapping
- ```
 ccv
 ```
 sets the cc value. normalized from 0 to 1.

> note("c a f e").control([74, sine.slow(4)]).midi()
> note("c a f e").ccn(74).ccv(sine.slow(4)).midi()

In the above snippet,

```
ccn
```
is set to 74, which is the filter cutoff for many synths.
```
ccv
```
is controlled by a saw pattern.
Having everything in one pattern, the
```
ccv
```
pattern will be aligned to the note pattern, because the structure comes from the left by default.
But you can also control cc messages separately like this:
> $: note("c a f e").midi() $: ccv(sine.segment(16).slow(4)).ccn(74).midi()

Instead of setting

```
ccn
```
and
```
ccv
```
directly, you can also create mappings with
```
midimaps
```

## midimaps

Adds midimaps to the registry. Inside each midimap, control names (e.g. lpf) are mapped to cc numbers.

> midimaps({ mymap: { lpf: 74 } }) $: note("c a f e") .lpf(sine.slow(4)) .midimap('mymap') .midi()
> midimaps({ mymap: { lpf: { ccn: 74, min: 0, max: 20000, exp: 0.5 } }}) $: note("c a f e") .lpf(sine.slow(2).range(400,2000)) .midimap('mymap') .midi()

## defaultmidimap

configures the default midimap, which is used when no "midimap" port is set

> defaultmidimap({ lpf: 74 }) $: note("c a f e").midi(); $: lpf(sine.slow(4).segment(16)).midi();

## progNum (Program Change)

```
progNum
```
sends MIDI program change messages to switch between different presets/patches on your MIDI device.
Program change values should be numbers between 0 and 127.
> // Switch between programs 0 and 1 every cycle progNum("<0 1>").midi() // Play notes while changing programs note("c3 e3 g3").progNum("<0 1 2>").midi()

Program change messages are useful for switching between different instrument sounds or presets during a performance. The exact sound that each program number maps to depends on your MIDI device’s configuration.

## sysex, sysexid && sysexdata (System Exclusive Message)

```
sysex
```
sends MIDI System Exclusive (SysEx) messages to your MIDI device.
ysEx messages are device-specific commands that allow deeper control over synthesizer parameters.
The value should be an array of numbers between 0-255 representing the SysEx data bytes.
> // Send a simple SysEx message let id = 0x43; //Yamaha //let id = "0x00:0x20:0x32"; //Behringer ID can be an array of numbers let data = "0x79:0x09:0x11:0x0A:0x00:0x00"; // Set NSX-39 voice to say "Aa" $: note("c a f e").sysex(id, data).midi(); $: note("c a f e").sysexid(id).sysexdata(data).midi();

The exact format of SysEx messages depends on your MIDI device’s specification. Consult your device’s MIDI implementation guide for details on supported SysEx messages.

## midibend && miditouch

```
midibend
```
sets MIDI pitch bend (-1 - 1)

```
miditouch
```
sets MIDI key after touch (0-1)
> note("c a f e").midibend(sine.slow(4).range(-0.4,0.4)).midi()

> note("c a f e").miditouch(sine.slow(4).range(0,1)).midi()

# OSC/SuperDirt/StrudelDirt

In TidalCycles, sound is usually generated using SuperDirt, which runs inside SuperCollider. Strudel also supports using SuperDirt, although it requires installing some additional software.

There is also StrudelDirt which is SuperDirt with some optimisations for working with Strudel. (A longer term aim is to merge these optimisations back into mainline SuperDirt)

## Prequisites

To get SuperDirt to work with Strudel, you need to

1. install SuperCollider + sc3 plugins, see Tidal Docs (Install Tidal) for more info.
2. install SuperDirt, or the StrudelDirt fork which is optimised for use with Strudel
3. install node.js
4. download Strudel Repo (or git clone, if you have git installed)
5. run
 ```
 pnpm i
 ```
 in the strudel directory
6. run
 ```
 pnpm run osc
 ```
 to start the osc server, which forwards OSC messages from Strudel REPL to SuperCollider

Now you’re all set!

## Usage
1. Start SuperCollider, either using SuperCollider IDE or by running
 ```
 sclang
 ```
 in a terminal
2. Open the Strudel REPL

…or test it here:

If you now hear sound, congratulations! If not, you can get help on the #strudel channel in the TidalCycles discord.

Note: if you have the ‘Audio Engine Target’ in settings set to ‘OSC’, you do not need to add .osc() to the end of your pattern.

### Pattern.osc

Sends each hap as an OSC message, which can be picked up by SuperCollider or any other OSC-enabled software. For more info, read MIDI & OSC in the docs

## SuperDirt Params

Please refer to Tidal Docs for more info.

But can we use Strudel offline?

# MQTT

MQTT is a lightweight network protocol, designed for ‘internet of things’ devices. For use with strudel, you will need access to an MQTT server known as a ‘broker’ configured to accept secure ‘websocket’ connections. You could run one yourself (e.g. by running mosquitto), although getting an SSL certificate that your web browser will trust might be a bit tricky for those without systems administration experience. Alternatively, you can use a public broker.

Strudel does not yet support receiving messages over MQTT, only sending them.

## Usage

The following example shows how to send a pattern to an MQTT broker:

Other software can then receive the messages. For example using the mosquitto commandline client tools:

```

> mosquitto_sub -h mqtt.eclipseprojects.io -p 1883 -t "/strudel-pattern"
> hello
> world
> hello
> world
> ...

```

Control patterns will be encoded as JSON, for example:

Will send messages like the following:

```

{"s":"sax","speed":2}
{"s":"sax","speed":2}
{"s":"sax","speed":3}
{"s":"sax","speed":2}
...

```

Libraries for receiving MQTT are available for many programming languages.

```

```
