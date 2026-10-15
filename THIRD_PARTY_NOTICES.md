# Third-Party Notices

This repository is MIT-licensed (see `LICENSE`). One function contains code
structurally ported from a third-party project under a different license.
This notice satisfies that license's own attribution requirement (PSF
License Agreement v2, clause 3: "a brief summary of the changes made").

## `hooks/_lib/shell_parse.py` -- `_scan_tokens`

**Origin:** CPython's standard-library `Lib/shlex.py`, the `shlex.read_token`
method (present, unchanged in relevant part, in both Python 3.9 and 3.14).

**Summary of changes:** `_scan_tokens` implements only the single fixed
configuration `shlex.split` actually uses -- POSIX mode, `whitespace_split=True`,
no comments, no `punctuation_chars` -- so every branch specific to a
different `shlex` configuration (non-POSIX quoting, `commenters`,
`wordchars`, `punctuation_chars` / `_pushback_chars`) was removed as
unreachable for this use. Each token is accumulated in a local list and
joined once (`"".join(parts)`) instead of appended character-by-character to
a `self.token` instance attribute -- the change that makes this version
linear rather than quadratic in one token's length, which is the whole
reason this port exists. End-of-input is modeled as a single `None`
sentinel produced once, in place of `read_token`'s repeated
`self.instream.read(1)` / `not nextchar` checks. The original's named states
(`' '`, `'a'`, `'c'`, a quote character, or the escape character) are renamed
to `"ws"`, `"word"`, the quote character itself, and `"esc"`; the `'c'`
(punctuation-mode) state does not apply to this fixed configuration and was
dropped. The control flow is otherwise the same state machine as
`read_token`.

**License:** PSF License Agreement v2, reproduced verbatim below. Copied
from
`/opt/homebrew/opt/python@3.14/Frameworks/Python.framework/Versions/3.14/lib/python3.14/LICENSE.txt`
(the file `sys.base_prefix + "/lib/python3.14/LICENSE.txt"` for the
`/opt/homebrew/bin/python3` interpreter on this machine), section "PYTHON
SOFTWARE FOUNDATION LICENSE VERSION 2" only. That file also carries the
BeOpen, CNRI, and CWI historical license agreements that cover earlier
Python releases; those do not apply to this port (`shlex.py`'s `read_token`
carries no history under those licenses) and are not reproduced here.

```
PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2
--------------------------------------------

1. This LICENSE AGREEMENT is between the Python Software Foundation
("PSF"), and the Individual or Organization ("Licensee") accessing and
otherwise using this software ("Python") in source or binary form and
its associated documentation.

2. Subject to the terms and conditions of this License Agreement, PSF hereby
grants Licensee a nonexclusive, royalty-free, world-wide license to reproduce,
analyze, test, perform and/or display publicly, prepare derivative works,
distribute, and otherwise use Python alone or in any derivative version,
provided, however, that PSF's License Agreement and PSF's notice of copyright,
i.e., "Copyright (c) 2001 Python Software Foundation; All Rights Reserved"
are retained in Python alone or in any derivative version prepared by Licensee.

3. In the event Licensee prepares a derivative work that is based on
or incorporates Python or any part thereof, and wants to make
the derivative work available to others as provided herein, then
Licensee hereby agrees to include in any such work a brief summary of
the changes made to Python.

4. PSF is making Python available to Licensee on an "AS IS"
basis.  PSF MAKES NO REPRESENTATIONS OR WARRANTIES, EXPRESS OR
IMPLIED.  BY WAY OF EXAMPLE, BUT NOT LIMITATION, PSF MAKES NO AND
DISCLAIMS ANY REPRESENTATION OR WARRANTY OF MERCHANTABILITY OR FITNESS
FOR ANY PARTICULAR PURPOSE OR THAT THE USE OF PYTHON WILL NOT
INFRINGE ANY THIRD PARTY RIGHTS.

5. PSF SHALL NOT BE LIABLE TO LICENSEE OR ANY OTHER USERS OF PYTHON
FOR ANY INCIDENTAL, SPECIAL, OR CONSEQUENTIAL DAMAGES OR LOSS AS
A RESULT OF MODIFYING, DISTRIBUTING, OR OTHERWISE USING PYTHON,
OR ANY DERIVATIVE THEREOF, EVEN IF ADVISED OF THE POSSIBILITY THEREOF.

6. This License Agreement will automatically terminate upon a material
breach of its terms and conditions.

7. Nothing in this License Agreement shall be deemed to create any
relationship of agency, partnership, or joint venture between PSF and
Licensee.  This License Agreement does not grant permission to use PSF
trademarks or trade name in a trademark sense to endorse or promote
products or services of Licensee, or any third party.

8. By copying, installing or otherwise using Python, Licensee
agrees to be bound by the terms and conditions of this License
Agreement.
```
