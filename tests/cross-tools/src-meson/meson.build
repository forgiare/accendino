# the meson flavour of crosstools: when cross compiling, protoc and the dependencies looked up with native: true
# must come from the build machine prefix, the other dependencies from the target prefix
project('crosstools-meson', 'c')

protoc = find_program('protoc', native: true)

foreach d : [
    [dependency('protobuf', native: true), get_option('build_prefix'), 'native'],
    [dependency('protobuf'), get_option('target_prefix'), 'target'],
  ]
  prefix = d[0].get_variable(pkgconfig: 'prefix')
  if prefix != d[1]
    error('@0@ protobuf found in @1@ instead of @2@'.format(d[2], prefix, d[1]))
  endif
  message('@0@ protobuf @1@ found in @2@'.format(d[2], d[0].version(), prefix))
endforeach

custom_target('hello-pb',
  input: 'hello.proto',
  output: ['hello.pb.cc', 'hello.pb.h'],
  command: [protoc, '--cpp_out=@OUTDIR@', '-I@CURRENT_SOURCE_DIR@', '@INPUT@'],
  build_by_default: true,
)

executable('crosstools-meson', 'main.c', install: true)
