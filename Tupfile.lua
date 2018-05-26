
tup.include('fibre/tupfiles/build.lua')
tup.include('fibre/cpp/package.lua')

CPP_SOURCES = {'lightd.cpp','fibre/cpp/posix_tcp.cpp','fibre/cpp/protocol.cpp'}
INCLUDE = {'fibre/cpp/include'}
LIBS = {'pthread', 'rt'}
CFLAGS = {}
LDFLAGS = {}

TOOLCHAIN = 'arm-linux-gnueabihf-' -- cross-compile
--TOOLCHAIN = '' -- compile for the current architecture

-- C sources
rpi_ws281x_package = define_package{
    sources={
        'rpi_ws281x/mailbox.c',
        'rpi_ws281x/ws2811.c',
        'rpi_ws281x/pwm.c',
        'rpi_ws281x/pcm.c',
        'rpi_ws281x/dma.c',
        'rpi_ws281x/rpihw.c'
    }
}

lightd = define_package{
    packages={
        fibre_package,
        rpi_ws281x_package
    },
    sources={'lightd.cpp'}
}

toolchain=GCCToolchain(TOOLCHAIN, 'build', {'-O3', '-g', '-D_XOPEN_SOURCE=500'}, {})
build_executable('lightd', lightd, toolchain)

