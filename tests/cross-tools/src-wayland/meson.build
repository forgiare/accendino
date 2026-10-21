# the wayland flavour of crosstools: wayland-scanner runs on the build machine. The generated code needs the wayland
# headers of the target, the test only generates it
project('crosstools-wayland', 'c')

scanner_dep = dependency('wayland-scanner', native: true)
scanner = find_program(scanner_dep.get_variable(pkgconfig: 'wayland_scanner'), native: true)
message('wayland-scanner @0@: @1@'.format(scanner_dep.version(), scanner.full_path()))

foreach kind : [['client-header', 'accendino-hello-client-protocol.h'], ['private-code', 'accendino-hello-protocol.c']]
  custom_target(kind[0],
    input: 'accendino-hello.xml',
    output: kind[1],
    command: [scanner, kind[0], '@INPUT@', '@OUTPUT@'],
    build_by_default: true,
  )
endforeach

executable('crosstools-wayland', 'main.c', install: true)
