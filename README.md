# Accendino, an Ogon installer

## About
_Accendino_ (lighter in italian) is an helper script that avoids the burden of following Ogon installation
instructions and do it for you.

_Accendino_ can also be used to checkout all ogon sources if you wish to quickly have a development environment.

Please note, that for now _accendino_ doesn't perform system operation required for a working ogon installation 
(systemd units, PAM configuration, dbus authorizations). So refer to the ogon build guide to achieve these.

To quicky install all the Ogon stack in `/opt/ogon` in release mode:

```console
# python accendino.py --prefix=/opt/ogon
```

To quicky install only the Ogon RDP server in `/opt/ogon-dev` in debug mode:

```console
# python accendino.py --prefix=/opt/ogon-dev --build-type=debug --targets=ogon-freerdp2
```


## Custom source file
_Accendino_ can also be used to pull your own sources and build a custom version of Ogon, to achieve this you
can ship a _source_ file that is a python script listing new dependencies and packages to build. The [forgiare](forgiare.conf) 
file give an example of such capacity, it will substitute the official ogon repo with over the edge changes.

_Accendino_ will read source file and will search for 3 variables:

* `DEFAULT_TARGETS` : contains the item to build by default when no target is given on the command line;
* `BUILD_ITEMS` : contains a list of items to build with their source locations and actions to build;
* `ITEMS_PKG`  : contains a map of package requirements by distro / version;
