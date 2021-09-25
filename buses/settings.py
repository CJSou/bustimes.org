"""These settings rely on various environment variables being set
"""

import os
import sys
from pathlib import Path
from aioredis import ReplyError
from autobahn.exception import Disconnected


BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ['SECRET_KEY']
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split()

TEST = 'test' in sys.argv or 'pytest' in sys.argv[0]
DEBUG = bool(os.environ.get('DEBUG', False))

SERVER_EMAIL = 'contact@bustimes.org'
DEFAULT_FROM_EMAIL = 'bustimes.org <contact@bustimes.org>'

if TEST:
    EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
else:
    EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
    EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
    EMAIL_PORT = 465
    EMAIL_USE_SSL = True
    EMAIL_TIMEOUT = 10

INSTALLED_APPS = [
    'accounts',
    'busstops',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',
    'django.contrib.sitemaps',
    'bustimes',
    'disruptions',
    'fares',
    'vehicles',
    'vosa',
    'antispam',
    'email_obfuscator',
    'channels',
    'api',
    'rest_framework',
    'django_filters'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'beeline.middleware.django.HoneyMiddleware',
]

SECURE_REFERRER_POLICY = None

if DEBUG and 'runserver' in sys.argv:
    INTERNAL_IPS = ['127.0.0.1']
    INSTALLED_APPS.append('debug_toolbar')
    MIDDLEWARE += [
        'debug_toolbar.middleware.DebugToolbarMiddleware',
        'debug_toolbar_force.middleware.ForceDebugToolbarMiddleware',
    ]

ROOT_URLCONF = 'buses.urls'

ASGI_APPLICATION = 'vehicles.routing.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': os.environ.get('DB_NAME', 'bustimes'),
        'CONN_MAX_AGE': None,
        # 'DISABLE_SERVER_SIDE_CURSORS': True,
        'OPTIONS': {
            'application_name': os.environ.get('APPLICATION_NAME') or ' '.join(sys.argv)[:63],
            'connect_timeout': 3
        },
        'TEST': {
            'SERIALIZE': False
        }
    }
}
TEST_RUNNER = 'django_slowtests.testrunner.DiscoverSlowestTestsRunner'
NUM_SLOW_TESTS = 20

AUTH_USER_MODEL = 'accounts.User'
LOGIN_REDIRECT_URL = '/vehicles'

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 100
}

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

if os.environ.get('READ_ONLY_DB_HOST'):
    REPLICA_DATABASES = []
    for i, host in enumerate(os.environ['READ_ONLY_DB_HOST'].split()):
        key = f'read-only-{i}'
        DATABASES[key] = DATABASES['default'].copy()
        DATABASES[key]['HOST'] = host
        REPLICA_DATABASES.append(key)
    DATABASE_ROUTERS = ['multidb.PinningReplicaRouter']
    MIDDLEWARE.append('busstops.middleware.pin_db_middleware')
    READ_DATABASE = key
else:
    READ_DATABASE = 'default'

DATA_UPLOAD_MAX_MEMORY_SIZE = None
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', REDIS_URL)
CELERY_RESULT_BACKEND = CELERY_BROKER_URL

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [CELERY_BROKER_URL],
            'expiry': 20
        }
    }
}


STATIC_URL = '/static/'
STATIC_ROOT = os.environ.get('STATIC_ROOT', BASE_DIR.parent / 'bustimes-static')
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

TEMPLATE_MINIFER_STRIP_FUNCTION = 'buses.utils.minify'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'OPTIONS': {
            'debug': DEBUG or TEST,  # required by django_coverage_plugin
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
            'loaders': [('django.template.loaders.cached.Loader', [
                'template_minifier.template.loaders.app_directories.Loader'
            ])]
        }
    }
]
if DEBUG:
    TEMPLATES[0]['OPTIONS']['loaders'] = ['django.template.loaders.app_directories.Loader']
elif TEST:
    TEMPLATES[0]['OPTIONS']['loaders'] = [('django.template.loaders.cached.Loader', [
        'django.template.loaders.app_directories.Loader'
    ])]


CACHES = {}
if TEST:
    CACHES["default"] = {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache"
    }
else:
    CACHES["default"] = {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }


VARNISH_HOST = os.environ.get('VARNISH_HOST')
VARNISH_PORT = os.environ.get('VARNISH_PORT')
if VARNISH_HOST and VARNISH_PORT:
    VARNISH = (VARNISH_HOST, int(VARNISH_PORT))
else:
    VARNISH = None

TIME_FORMAT = 'H:i'
DATE_FORMAT = 'l j F Y'
DATETIME_FORMAT = 'j M H:i'
TIME_ZONE = 'Europe/London'
USE_TZ = True
USE_I18N = False


def before_send(event, hint):
    if 'exc_info' in hint:
        exc_type, exc_value, traceback = hint['exc_info']
        if isinstance(exc_value, ReplyError) or isinstance(exc_value, Disconnected):
            return
    return event


if TEST:
    pass
elif not DEBUG and 'collectstatic' not in sys.argv and 'SENTRY_DSN' in os.environ:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=os.environ['SENTRY_DSN'],
        integrations=[DjangoIntegration(), RedisIntegration(), CeleryIntegration()],
        ignore_errors=[KeyboardInterrupt],
        before_send=before_send
    )
if not TEST:
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
            },
        },
        'root': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    }

TFL = {
    'app_id': os.environ.get('TFL_APP_ID'),
    'app_key': os.environ.get('TFL_APP_KEY')
}
TFWM = {
    'app_id': os.environ.get('TFWM_APP_ID'),
    'app_key': os.environ.get('TFWM_APP_KEY')
}

DATA_DIR = BASE_DIR / 'data'
TNDS_DIR = DATA_DIR / 'TNDS'

AKISMET_API_KEY = os.environ.get('AKISMET_API_KEY')
AKISMET_SITE_URL = 'https://bustimes.org'

# see bustimes.management.commands.import_passenger
PASSENGER_OPERATORS = [
    ('Go Cornwall Bus', 'https://www.gocornwallbus.co.uk/open-data', 'SW', {
        'TFCN': 'TFCN',
        'TfCN': 'TFCN'
    }),
    ('Plymouth Citybus', 'https://www.plymouthbus.co.uk/open-data', 'SW', {
        'PLYC': 'PLYC'
    }),
    ('Go North West', 'https://www.gonorthwest.co.uk/open-data', 'NW', {
        'GONW': 'GONW'
    }),
    ('Oxford Bus Company', 'https://data.discoverpassenger.com/operator/oxfordbus', 'SE', {
        'OXBC': 'OXBC',
        'THTR': 'THTR'
    }),
    ('Carousel', 'https://data.discoverpassenger.com/operator/carouselbuses', 'SE', {
        'CSLB': 'CSLB'
    }),
    ('Metrobus', 'https://www.metrobus.co.uk/open-data', 'SE', {
        'METR': 'METR'
    }),
    ('Nottingham City Transport', 'https://www.nctx.co.uk/open-data', 'EM', {
        'NCT': 'NCTR'
    }),
    ('Borders Buses', 'https://www.bordersbuses.co.uk/open-data', 'S', {
        'PERY': 'BORD',
        'BB': 'BORD',
        '': 'PERY',
    }),
    ('morebus', 'https://www.morebus.co.uk/open-data', 'SW', {
        'SQ': 'WDBC',
        'DAM': 'DAMY',
        'BLU': 'BLUS',
    }),
    ('UNIBUS', 'https://www.unibuses.co.uk/open-data', 'SW', {
        'SQ': 'WDBC',
    }),
    ('Bluestar', 'https://www.bluestarbus.co.uk/open-data', 'SW', {
        'SQ': 'BLUS',
        'UNIL': 'UNIL',
    }),
    ('Unilink', 'https://www.unilinkbus.co.uk/open-data', 'SW', {
        'SQ': 'UNIL',
        'BLUS': 'BLUS',
    }),
    ('Salisbury Reds', 'https://www.salisburyreds.co.uk/open-data', 'SW', {
        'SQ': 'SWWD',
        'SR': 'SWWD',
        'DAM': 'DAMY',
    }),
    ('Southern Vectis', 'https://www.islandbuses.info/open-data', 'SW', {
        'SQ': 'SVCT',
        'DAM': 'DAMY',
    }),

    ('Reading Buses', 'https://www.reading-buses.co.uk/open-data', 'SE', {
        'RBUS': 'RBUS',
    }),
    ('Thames Valley Buses', 'https://www.thamesvalleybuses.com/open-data', 'SE', {
        'THVB': 'THVB',
        'CTNY': 'CTNY',
    }),
    ('Newbury & District', 'https://data.discoverpassenger.com/operator/kennections', 'SE', {
        'NADS': 'NADS',
    }),

    ('West Coast Motors', 'https://www.westcoastmotors.co.uk/open-data', 'S', {
        'WCM': 'WCMO',
        'GCB': 'GCTB',  # Glasgow Citybus
    }),
    ('Cardiff Bus', 'https://www.cardiffbus.com/open-data', 'W', {
        'CB': 'CBUS',
        # 'NB': '',
    }),
    ('Yellow Buses', 'https://www.yellowbuses.co.uk/open-data', 'SW', {
        'YELL': 'YELL',
    }),
    ('Swindon’s Bus Company', 'https://www.swindonbus.co.uk/open-data', 'SW', {
        'TT': 'TDTR',
        'SBCR': 'TDTR',  # rural
        'SR': 'TDTR',  # rural
        'SWIN': 'TDTR',
        'NATI': 'TDTR',  # Nationwide Building Society
    }),
    ('Brighton & Hove Buses', 'https://www.buses.co.uk/open-data', 'SE', {
        'BH': 'BHBC',
    }),
    ('East Yorkshire', 'https://www.eastyorkshirebuses.co.uk/open-data', 'Y', {
        'EY': 'EYMS',
    }),
    ('Blackpool Transport', 'https://www.blackpooltransport.com/open-data', 'NW', {
        'RR': 'BLAC',
    }),
    ('Transdev Blazefield', 'https://www.transdevbus.co.uk/open-data', 'NW', {
        'LUI': 'LNUD',
        'ROS': 'ROST',
        'BPT': 'BPTR',
        'KDT': 'KDTR',
        'HDT': 'HRGT',
        'YCD': 'YCST',
        'TPEN': 'TPEN',
    }),
    ('Go North East', 'https://www.gonortheast.co.uk/open-data', 'NE', {
        'GNE': 'GNEL',
    }),
    ('McGill’s', 'https://data.discoverpassenger.com/operator/mcgills', 'S', {
        'MCG': 'MCGL',
        'McG': 'MCGL',
    }),
    ('Warringtons Own Buses', 'https://www.warringtonsownbuses.co.uk/open-data', 'NW', {
        'WOB': 'WBTR',
    }),
    ('Newport Bus', 'https://www.newportbus.co.uk/open-data', 'W', {
        'NWPT': 'NWPT',
    }),
]

# see bustimes.management.commands.import_bod
BOD_OPERATORS = [
    ('FBOS', None, {
        'FYOR': 'FYOR',
        # 'FPOT': 'FPOT',
        # 'FSYO': 'FSYO',
        # 'FMAN': 'FMAN',
        # 'FLDS': 'FLDS',
        # 'FHUD': 'FHUD',
        # 'FSMR': 'FSMR',
        # 'FHAL': 'FHAL',
        # 'FBRA': 'FBRA',
        # 'FESX': 'FESX',
        'FECS': 'FECS',
        # 'FCWL': 'FCWL',
        # 'FHDO': 'FHDO',
        'FTVA': 'FTVA',
        # 'FHAM': 'FHAM',
        # 'FDOR': 'FDOR',
        # 'FBOS': 'FBOS',
        # 'FLEI': 'FLEI',
        'RRAR': 'RRAR',
        'FBRI': 'FBRI',
        # 'ABUS': 'ABUS',
        # 'FWYO': 'FWYO',
    }, True),
    ('AKSS', None, {
        'ACYM': 'ACYM',
        'ADER': 'ADER',
        'AFCL': 'AFCL',
        'AKSS': 'AKSS',
        'AMAN': 'AMAN',
        'AMID': 'AMID',
        'AMNO': 'AMNO',
        'AMSY': 'AMSY',
        'AMTM': 'AMTM',
        'ANEA': 'ANEA',
        'ANUM': 'ANUM',
        'ANWE': 'ANWE',
        'ARBB': 'ARBB',
        'ARDU': 'ARDU',
        'ARHE': 'ARHE',
        'ASES': 'ASES',
        'GLAR': 'GLAR',
        'WRAY': 'WRAY',
        'YTIG': 'YTIG',
    }, False),
    ('TNXB', 'WM', {
        'TNXB': 'TNXB',
        'TCVW': 'TCVW',
    }, False),
    ('UNOE', 'SE', {
        'UBN': 'UNOE',
        'UNIB': 'UNOE',
        'OP': 'UNOE',
        'UN': 'UNOE',
    }, False),
    ('TBTN', 'EM', {
        'BRTB': 'TBTN',
    }, False),
    ('KBUS', 'EM', {}, False),

    ('CSVC', 'EA', {
        'CS': 'CSVC'
    }, False),
    ('HIPK', 'EM', {
        'OP': 'HIPK',
        'HPB': 'HIPK',
    }, False),
    ('HNTS', 'EM', {}, False),
    # ('SLBS', 'WM', {}, True),

    ('LODG', 'SE', {}, False),
    ('FRDS', 'SE', {}, False),

    ('AVMT', 'SW', {}, False),
    ('BZCO', 'SW', {}, False),
    ('C2WI', 'SW', {}, False),
    ('CNTY', 'SW', {}, False),
    ('COAC', 'SW', {}, False),
    ('COTS', 'SW', {}, False),
    ('CRYC', 'SW', {}, False),
    ('DTCO', 'SW', {}, False),
    ('FRMN', 'SW', {}, False),
    ('FSRV', 'SW', {}, False),
    ('FTZL', 'SW', {}, False),
    ('GWIL', 'SW', {}, False),
    ('HGCO', 'SW', {}, False),
    ('HOPE', 'SW', {}, False),
    ('JACK', 'SW', {}, False),
    ('LTRV', 'SW', {}, False),
    ('NAKL', 'SW', {}, False),
    ('OTSS', 'SW', {}, False),
    ('PULH', 'SW', {}, False),
    ('RIDL', 'SW', {}, False),
    ('RSLN', 'SW', {}, False),
    ('SMST', 'SW', {}, False),
    ('SWCO', 'SW', {}, False),
    ('TAWT', 'SW', {}, False),
    ('TLYH', 'SW', {}, False),
    ('TOTN', 'SW', {}, False),
    ('YEOS', 'SW', {}, False),
    ('SMMC', 'SW', {}, False),
    ('GYLC', 'SW', {}, False),
    ('SWAN', 'SW', {}, False),
    ('CTCO', 'SW', {}, False),
    ('EBLY', 'SW', {}, False),
    ('BYCO', 'SW', {}, False),
    ('NEJH', 'SW', {}, False),
    ('BNNT', 'SW', {}, False),
    ('XLBL', 'SW', {}, False),
    ('NCSL', 'SW', {}, False),
    ('AMKC', 'SW', {}, False),
    ('EUTX', 'SW', {}, False),
    ('CHCB', 'SW', {}, False),
    ('DJWA', 'SW', {}, False),
    ('BNSC', 'SW', {}, False),
    ('MARC', 'SW', {}, False),
    ('NRTL', 'SW', {}, False),
    ('PRIC', 'SW', {}, False),
    ('LIHO', 'SW', {}, False),
    ('DPCR', 'SW', {}, False),

    # ('NATX', 'GB', {}, False),
    ('KETR', 'SE', {}, False),
    # ('HACO', 'EA', {}, False),
    # ('PCCO', 'EM', {}, False),
    ('HCCL', 'NE', {
        'HCC': 'WGHC'
    }, False),

    ('SPSV', 'SE', {}, False),
    ('GOCH', 'SE', {
        'GO': 'GOCH'
    }, False),

    ('LAKC', 'WM', {}, True),  # incomplete

    ('CBBH', 'EM', {
        'CBBH': 'CBBH',
        'CBNL': 'CBNL',
        'CBL': 'CBNL',
    }, False),
    # ('BULL', 'NW', {}, False),
    ('SELT', 'NW', {}, False),  # Selwyns Ticketer
    ('ROSS', 'Y',  {}, False),  # Ross Travel Ticketer

    ('GRYC', 'EM',  {}, False),

    # ('A2BR', 'EA',  {}, False),
    # ('A2BV', 'NE',  {}, False),

    ('STNE', 'NE',  {}, False),
    ('LAWS', 'EM',  {}, False),
    ('BMCS', 'SE',  {}, False),

    ('CPLT', 'EA', {}, False),
    ('OBUS', 'EA', {
        'OURH': 'OURH',
        'OBUS': 'OBUS',
    }, False),

    ('WNGS', None, {  # Rotala Group of Companies
        'WINGS': 'WNGS',
        'TGM': 'WNGS',  # Diamond SE
        'NXHH': 'NXHH',  # Hotel Hoppa
        'DIAM': 'DIAM',  # Diamond WM
        'GTRI': 'GTRI',  # Diamond NW
        'PBLT': 'PBLT',  # Preston
    }, False),

    ('PLNG', 'EA', {}, False),
    ('SNDR', 'EA', {}, False),
    ('STOT', 'NW', {}, False),
    ('CARL', 'SE', {}, False),
    ('IRVD', 'NW', {}, False),
    ('FALC', 'SE', {}, False),
    ('VECT', 'SE', {}, False),
    ('ACME', 'SE', {}, False),

    ('VIKG', 'NW', {}, False),  # Viking
    ('ALSC', 'NW', {}, False),  # Happy Al's
    ('LCAC', 'NW', {}, False), 
    ('LNNE', 'NW', {}, False), 

    ('RBUS', 'SE', {}, True),  # incomplete

    ('ROOS', 'SW', {}, False),
    ('SEWR', 'SW', {}, False),
    ('HRBT', 'SE', {}, False),
    ('KENS', 'Y', {}, False),
    ('AWAN', 'SE', {}, False),
    ('LUCK', 'SW', {}, False),

    ('GVTR', 'NE', {}, False),
    ('COTY', 'NE', {}, False),

    ('LMST', 'WM', {}, False),
    ('TEXP', 'WM', {}, False),
    ('BANG', 'WM', {}, False),
    ('SLVL', 'WM', {}, False),
    ('JOHS', 'WM', {}, False),

    ('ENSB', 'SE', {}, False),

    ('BRYL', 'EM', {}, False),
    ('MDCL', 'EM', {}, False),
    ('NDTR', 'EM', {}, False),
    ('NOCT', 'EM', {}, False),

    ('RELD', 'Y', {}, False),
    ('SSSN', 'Y', {}, False),
    ('KJTR', 'Y', {}, False),
    ('HCTY', 'Y', {
        'HCTY': 'HCTY',  # Connexions
        'YRRB': 'YRRB',  # 'Road Runner'
    }, False),

    ('NCTP', None, {
        'NCTP': 'NCTP',  # CT Plus Bristol (/London)
        'POWB': 'POWB',  # Powells
        'CTPL': 'CTPL',  # CT Plus Yorkshire
    }, False),

    ('LYNX', 'EA', {}, False),
    ('IPSW', 'EA', {}, False),
    ('WNCT', 'EA', {}, False),
    ('WHIP', 'EA', {}, False),
    ('SIMO', 'EA', {}, False),
    ('BEES', 'EA', {}, False),
    ('GOGO', 'NW', {}, False),
    ('RBTS', 'EM', {}, False),
    ('DELA', 'EM', {}, False),
    ('RLNE', 'SE', {}, False),
    ('HATT', 'NW', {}, False),
    ('SULV', 'SE', {}, False),
    ('WBSV', 'SE', {}, False),
    ('REDE', 'SE', {}, False),
    ('GPLM', 'SE', {}, False),
    ('CLNB', 'SE', {}, False),
    ('RRTR', 'SE', {}, False),
    ('RCHC', 'SE', {}, False),
    ('FCHS', 'NW', {}, False),
    ('CRSS', 'WM', {}, True),  # NN Cresswell
    ('DAGC', None, {
        'DAGC': 'DAGC',
        'CRDR': 'CRDR'
    }, False),
    # ('Go East Anglia', 'EA', {
    #     'KCTB': 'KCTB',
    #     'HEDO': 'HEDO',
    #     'CHAM': 'CHAM',
    # }, False),

    ('DRMC', 'WM', {}, True),
    ('SARG', 'WM', {}, False),

    ('AMBS', 'EA', {
        'AMBS': 'AMBS',
        'SEMM': 'SEMM',
    }, True),

    ('RDRT', 'SE', {
        'RR': 'RDRT',
        'RR1': 'RDRT'
    }, False),
]

# see bustimes.management.commands.import_bod
STAGECOACH_OPERATORS = [
    ('S',  'sblb', 'Stagecoach Bluebird',      ['SBLB']),
    ('S',  'scfi', 'Stagecoach East Scotland', ['SCFI', 'SCPE', 'SSPH', 'STSY', 'SSTY']),
    ('S',  'schi', 'Stagecoach Highlands',     ['SCHI', 'SCOR', 'SINV']),
    ('NE', 'scne', 'Stagecoach North East',    ['SCNE', 'SCSS', 'SCSU', 'SCTE', 'SCHA']),
    ('S',  'stws', 'Stagecoach West Scotland', ['STWS', 'SCGS', 'STGS']),
    ('EM', 'scem', 'Stagecoach East Midlands', ['SCLI', 'SCGH', 'SCGR', 'NFKG']),
    ('SE', 'scso', 'Stagecoach South',         ['SCPY', 'SCHM', 'SCHW', 'SCCO', 'SMSO', 'SCHS', 'SCHN']),
    ('SE', 'scek', 'Stagecoach South East',    ['SCEK', 'SCEB', 'SCHT']),
    ('Y',  'syrk', 'Stagecoach Yorkshire',     ['SYRK', 'YSYC', 'CLTL']),
    ('NW', 'sccu', 'Stagecoach Cumbria',       ['SCCU', 'SCMB', 'SCNW']),
    ('NW', 'scmn', 'Stagecoach Manchester',    ['SCMN', 'SWIG']),
    ('NW', 'scmy', 'Stagecoach Merseyside',    ['SCMY', 'STCR', 'STWR', 'SCLA']),
    ('SW', 'sdvn', 'Stagecoach South West',    ['SDVN', 'SDVN']),
    ('SE', 'sccm', 'Stagecoach East',          ['SCCM', 'SCBD', 'SCPB', 'SCHU']),
    ('EM', 'scnh', 'Stagecoach Midlands',      ['SCNH', 'SCWW']),
    ('SE', 'scox', 'Stagecoach Oxfordshire',   ['SCOX']),
    ('SW', 'scgl', 'Stagecoach West',          ['SCGL', 'SSWN', 'STWD', 'SCCH']),
    ('W',  'sswl', 'Stagecoach South Wales',   ['SSWL']),
    ('Y',  'tram', 'Stagecoach Supertram',     ['SCST']),
]

# Some operators' timetables are fetched directly from e.g.
# https://opendata.ticketer.com/uk/LYNX/routes_and_timetables/current.zip
# rather than via the Bus Open Data site,
# because sometimes BODS doesn't detect updates
TICKETER_OPERATORS = [
    ('EA', ['GOEA', 'KCTB', 'HEDO', 'CHAM'], 'Go East Anglia'),
    ('EA', ['BDRB'], 'BorderBus'),
]
