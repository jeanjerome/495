"""What the harness concludes from what it measured, computed and nothing else.

A module here is a function of the documents and the strings it is handed: it reads a diff, a
runner's output, a pair of runs, a specification, and says what they mean. It executes no
command, opens no file of the project and writes nothing. What executes lives in
``core/engine/``, which hands these readers what it measured.
"""
