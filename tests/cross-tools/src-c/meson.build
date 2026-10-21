# the protobuf-c flavour of crosstools: protoc and protoc-gen-c run on the build machine, the generated code is
# linked with the libprotobuf-c of the target
project('crosstools-c', 'c')

protoc = find_program('protoc', native: true)
protoc_gen_c = find_program('protoc-gen-c', native: true)
protobuf_c = dependency('libprotobuf-c')

hello_pb = custom_target('hello-pb-c',
  input: 'hello.proto',
  output: ['hello.pb-c.c', 'hello.pb-c.h'],
  command: [protoc, '--plugin=protoc-gen-c=' + protoc_gen_c.full_path(), '--c_out=@OUTDIR@', '-I@CURRENT_SOURCE_DIR@',
            '@INPUT@'],
)

executable('crosstools-c', 'main.c', hello_pb, dependencies: protobuf_c, install: true)
