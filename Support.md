# Accendino support by platforms

This files gives some information on what is supported by _Accendino_ by platforms, so in terms of
linux distributions, native package manager, cross compiling possibilities, ...

## Linux

In terms of package managers we support: `pacman`, `dpkg`, `rpm`. That means that we can list the installed
packages and possibly install them.

Accendino has been tested on:
* Ubuntu (22.04, 24.04)
* Debian (12)
* Fedora (41)
* Arch

Cross compiling with `mingw` from linux to windows works with at least Ubuntu, Debian and Fedora.

## FreeBSD

There's preliminary support for FreeBSD (tested on 14.1) using the `pkg` package manager.

## Windows

Right now we support `Chocolatey` as package manager. We can build at least FreeRDP3 with VisualStudio 2022 but
other version may work.

## MacOs

Under MacOS we support the `brew` package manager.