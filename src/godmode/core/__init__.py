"""Core foundations: config, paths, logging, money math, database, audit log, kill switch.

These modules have no dependency on any trading venue or LLM provider, so they can be
imported and tested in isolation. Everything else builds on top of them.
"""
