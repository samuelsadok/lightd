
#include <stdio.h>
#include <unistd.h>
#include <thread>
#include <signal.h>

#include <fibre/protocol.hpp>
#include <fibre/posix_tcp.hpp>
#include <fibre/posix_udp.hpp>

#include "rpi_ws281x/ws2811.h"

constexpr unsigned int LEDSTRIP1_LENGTH = 167;
constexpr unsigned int LEDSTRIP2_LENGTH = 109;

ws2811_t ledstrip = {
    .render_wait_time = 0,
    .device = nullptr,
    .rpi_hw = nullptr,
    .freq = WS2811_TARGET_FREQ,
    .dmanum = 4,
    .channel = {
        [0] = {
            .gpionum = 18,
            .invert = 0,
            .count = LEDSTRIP1_LENGTH,
            .strip_type = SK6812_STRIP_GRBW,
            .leds = nullptr,
            .brightness = 255,
            .wshift = 0, .rshift = 0, .gshift = 0, .bshift = 0,
            .gamma = nullptr
        },
        [1] = {
            .gpionum = 13,
            .invert = 1,
            .count = LEDSTRIP2_LENGTH,
            .strip_type = SK6812_STRIP_GRBW,
            .leds = nullptr,
            .brightness = 255,
            .wshift = 0, .rshift = 0, .gshift = 0, .bshift = 0,
            .gamma = nullptr
        },
    },
};



// TODO: change to L*u*v* color space
typedef struct {
    float w, r, g, b;
} rgbw_t;

// alpha: 0...1 corresponds to color1...color2
static rgbw_t rgbw_blend(rgbw_t color1, rgbw_t color2, float alpha) {
    return {
        .w = color1.w * (1 - alpha) + color2.w * alpha,
        .r = color1.r * (1 - alpha) + color2.r * alpha,
        .g = color1.g * (1 - alpha) + color2.g * alpha,
        .b = color1.b * (1 - alpha) + color2.b * alpha,
    };
}

// returns a brightness in [0...1]
static float get_brightness(rgbw_t &color) {
    // relative brighness of each color channel
    static rgbw_t scale = { .w = 5, .r = 3, .g = 4, .b = 2 };
    return (color.w * scale.w + color.r * scale.r
            + color.g * scale.g + color.b * scale.b) /
            (scale.w + scale.r + scale.g + scale.b);
}

static rgbw_t limit_brightness(rgbw_t color, rgbw_t reference_color) {
    float brightness = get_brightness(color);
    float ref_brightness = get_brightness(reference_color);
    if (ref_brightness < brightness) {
        float scale = ref_brightness / brightness;
        return {
            .w = color.w * scale,
            .r = color.r * scale,
            .g = color.g * scale,
            .b = color.b * scale,
        };
    } else {
        return color;
    }
}

static float get_timespan(struct timespec *time1, struct timespec *time0) {
    return (float)(time1->tv_sec - time0->tv_sec) + (float)((time1->tv_nsec - time0->tv_nsec) / 1000000ll) / 1e3;
}



template<unsigned COUNT>
class LEDController {
public:
    LEDController() {
    }

    void start_fade(rgbw_t target, float duration, bool should_limit_brightness = 0) {
        // TODO: thread safety
        if (clock_gettime(CLOCK_MONOTONIC, &fade_start_)) {
            fprintf(stderr, "clock failed\n");
            return;
        }
        fade_duration_ = duration;

        for (size_t i = 0; i < COUNT; ++i) {
            img_end_[i] = should_limit_brightness ? limit_brightness(target, img_current_[i]) : target;
            img_start_[i] = img_current_[i];
        }
    }

    void render(ws2811_led_t *leds) {
        render();
        for (size_t i = 0; i < COUNT; ++i) {
            rgbw_t *color = &img_current_[i];
            leds[i] = ((uint32_t)(to_uint8(color->w) << 24) + (uint32_t)(to_uint8(color->r) << 16) +
                      (uint32_t)(to_uint8(color->g) << 8) + (uint32_t)(to_uint8(color->b) << 0));
        }
    }

    void set_color(float white, float red, float green, float blue, float duration, bool limit_brightness) {
        printf("set_color\n");
        start_fade((rgbw_t){
            .w = white,
            .r = red,
            .g = green,
            .b = blue
        }, duration, limit_brightness);
    }

    FIBRE_EXPORTS(LEDController,
        make_protocol_function("set_color", *obj, &LEDController::set_color, "white", "red", "green", "blue", "duration", "limit_brightness")
    );

private:
    void render() {
        struct timespec currenttime;
        if (clock_gettime(CLOCK_MONOTONIC, &currenttime)) {
            fprintf(stderr, "clock failed\n");
            return;
        }

        float progress = get_timespan(&currenttime, &fade_start_) / fade_duration_;
        if (!(progress < 1)) // also evaluates to true for inf and NaN
            progress = 1;
        for (size_t i = 0; i < COUNT; ++i)
            img_current_[i] = rgbw_blend(img_start_[i], img_end_[i], progress);
    }

    static uint8_t to_uint8(float val) {
        return (val <= 0) ? 0 : (val >= 1) ? 255 : static_cast<uint8_t>(val * 255.f);
    }

    rgbw_t img_current_[COUNT]; // 1-D image representing the current LED colors
    rgbw_t img_start_[COUNT];    // 1-D image at the beginning of the current animation
    rgbw_t img_end_[COUNT];      // 1-D image at the end of the current animation
    struct timespec fade_start_; // time when the fade started
    float fade_duration_;        // duration of the fade (can be 0, in which case the img_end is displayed)
};




LEDController<LEDSTRIP1_LENGTH> controller1;
LEDController<LEDSTRIP2_LENGTH> controller2;




class RootObject {
public:
    void set_color(float white, float red, float green, float blue, float duration, bool limit_brightness) {
        controller1.set_color(white, red, green, blue, duration, limit_brightness);
        controller2.set_color(white, red, green, blue, duration, limit_brightness);
    }
    FIBRE_EXPORTS(RootObject,
        make_protocol_function("set_color", *obj, &RootObject::set_color, "white", "red", "green", "blue", "duration", "limit_brightness"),
        make_protocol_object("ledstrip1", controller1.make_fibre_definitions()),
        make_protocol_object("ledstrip2", controller2.make_fibre_definitions())
    );
};

RootObject root_object;



static int running = 1;
static void sigterm_handler(int signum) {
	(void)(signum);
    running = 0;
}

int main() {
    ws2811_return_t ret = WS2811_SUCCESS;
    printf("Starting LED server...\n");

    // set up terminate-signals
    struct sigaction sa;
    sa.sa_handler = sigterm_handler;
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGTERM, &sa, NULL);

    // init LEDs
    if ((ret = ws2811_init(&ledstrip)) != WS2811_SUCCESS) {
        fprintf(stderr, "ws2811_init failed: %s\n", ws2811_get_return_t_str(ret));
        return ret;
    }

    // expose service on Fibre
    auto definitions = root_object.fibre_definitions;
    fibre_publish(definitions);

    // Expose Fibre objects on TCP and UDP
    std::thread server_thread_tcp(serve_on_tcp, 9910);
    std::thread server_thread_udp(serve_on_udp, 9910);
    printf("LED server started.\n");

    while (running) {
        // let the LED controllers render the LEDs
        controller1.render(ledstrip.channel[0].leds);
        controller2.render(ledstrip.channel[1].leds);
        
        // let the driver output the colors
        if ((ret = ws2811_render(&ledstrip)) != WS2811_SUCCESS) {
            fprintf(stderr, "ws2811_render failed: %s\n", ws2811_get_return_t_str(ret));
            break;
        }

        // 100 frames / sec
        usleep(1000000 / 100);
    }

    ws2811_fini(&ledstrip);

    return ret;
}
