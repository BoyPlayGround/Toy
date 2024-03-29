import imp
import sys
import logging

from contextlib import contextmanager
try:
    from urllib2 import urlopen
except:
    from urllib.request import urlopen

log_FORMAT = "%(message)s"
logging.basicConfig(format=log_FORMAT)
logger = logging.getLogger(__name__)
# logger.setLevel(logging.WARN)
logger.setLevel(logging.DEBUG)

NON_SOURCE = False
INSECURE = False
RELOAD = False


class GHImporter(object):

    def __init__(self, modules, base_url):
        self.module_names = modules
        self.base_url = base_url + '/'
        self.non_source = NON_SOURCE

        if not INSECURE and not self.__isHTTPS(base_url) :
            logger.warning("[-] '%s.INSECURE' is not set! Aborting..." % (__name__))
            raise Exception("Plain HTTP URL provided with '%s.INSECURE' not set" % __name__)

        if not self.__isHTTPS(base_url):
            logger.warning("[!] Using non HTTPS URLs ('%s') can be a security hazard!" % self.base_url)

    def find_module(self, fullname, path=None):
        logger.debug("FINDER=================")
        logger.debug("[!] Searching %s" % fullname)
        logger.debug("[!] Path is %s" % path)
        logger.info("[@] Checking if in declared remote module names >")
        if fullname.split('.')[0] not in self.module_names:
            logger.info("[-] Not found!")
            return None

        logger.info("[@] Checking if built-in >")
        try:
            loader = imp.find_module(fullname, path)
            if loader:
                logger.info("[-] Found locally!")
                return None
        except ImportError:
            pass
        logger.info("[@] Checking if it is name repetition >")
        if fullname.split('.').count(fullname.split('.')[-1]) > 1:
            logger.info("[-] Found locally!")
            return None

        logger.info("[*]Module/Package '%s' can be loaded!" % fullname)
        return self

    def load_module(self, name):
        imp.acquire_lock()
        logger.debug("LOADER=================")
        logger.debug("[+] Loading %s" % name)
        if name in sys.modules and not RELOAD:
            logger.info('[+] Module "%s" already loaded!' % name)
            imp.release_lock()
            return sys.modules[name]

        if name.split('.')[-1] in sys.modules and not RELOAD:
            logger.info('[+] Module "%s" loaded as a top level module!' % name)
            imp.release_lock()
            return sys.modules[name.split('.')[-1]]

        module_url = self.base_url + '%s.py' % name.replace('.', '/')
        package_url = self.base_url + '%s/__init__.py' % name.replace('.', '/')
        zip_url = self.base_url + '%s.zip' % name.replace('.', '/')
        final_url = None
        final_src = None

        try:
            logger.debug("[+] Trying to import as package from: '%s'" % package_url)
            package_src = None
            if self.non_source :    # Try the .pyc file
                package_src = self.__fetch_compiled(package_url)
            if package_src == None :
                package_src = urlopen(package_url).read()
            final_src = package_src
            final_url = package_url
        except IOError as e:
            package_src = None
            logger.info("[-] '%s' is not a package:" % name)

        if final_src == None:
            try:
                logger.debug("[+] Trying to import as module from: '%s'" % module_url)
                module_src = None
                if self.non_source :    # Try the .pyc file
                    module_src = self.__fetch_compiled(module_url)
                if module_src == None : # .pyc file not found, falling back to .py
                    module_src = urlopen(module_url).read()
                final_src = module_src
                final_url = module_url
            except IOError as e:
                module_src = None
                logger.info("[-] '%s' is not a module:" % name)
                logger.warning("[!] '%s' not found in HTTP repository. Moving to next Finder." % name)
                imp.release_lock()
                return None

        logger.debug("[+] Importing '%s'" % name)
        mod = imp.new_module(name)
        mod.__loader__ = self
        mod.__file__ = final_url
        if not package_src:
            mod.__package__ = name
        else:
            mod.__package__ = name.split('.')[0]

        mod.__path__ = ['/'.join(mod.__file__.split('/')[:-1]) + '/']
        logger.debug("[+] Ready to execute '%s' code" % name)
        sys.modules[name] = mod
        exec(final_src, mod.__dict__)
        logger.info("[+] '%s' imported succesfully!" % name)
        imp.release_lock()
        return mod

    def __fetch_compiled(self, url):
        import marshal
        module_src = None
        try:
            module_compiled = urlopen(url + 'c').read()  # from blah.py --> blah.pyc
            try:
                module_src = marshal.loads(module_compiled[8:]) # Strip the .pyc file header of Python up to 3.3
                return module_src
            except ValueError :
                pass
            try:
                module_src = marshal.loads(module_compiled[12:])# Strip the .pyc file header of Python 3.3 and onwards (changed .pyc spec)
                return module_src
            except ValueError :
                pass
        except IOError as e:
            logger.debug("[-] No compiled version ('.pyc') for '%s' module found!" % url.split('/')[-1])
        return module_src

    def __isHTTPS(self, url):
        return self.base_url.startswith('https')


@contextmanager
def remote_repo(modules, base_url='http://localhost:8000/'):
    importer = add_remote_repo(modules, base_url)
    yield
    remove_remote_repo(base_url)


def add_remote_repo(modules, base_url='http://localhost:8000/'):
    importer = GHImporter(modules, base_url)
    sys.meta_path.insert(0, importer)
    return importer


def remove_remote_repo(base_url):
    for importer in sys.meta_path:
        try:
            if importer.base_url.startswith(base_url):  # an extra '/' is always added
                sys.meta_path.remove(importer)
                return True
        except AttributeError as e:
            pass
    return False


def __create_github_url(username, repo, branch='master'):
    github_raw_url = 'https://raw.githubusercontent.com/{user}/{repo}/{branch}/'
    return github_raw_url.format(user=username, repo=repo, branch=branch)


def _add_git_repo(url_builder, username=None, repo=None, module=None, branch=None, commit=None):
    if username == None or repo == None:
        raise Error("'username' and 'repo' parameters cannot be None")
    if commit and branch:
        raise Error("'branch' and 'commit' parameters cannot be both set!")

    if commit:
        branch = commit
    if not branch:
        branch = 'master'
    if not module:
        module = repo
    if type(module) == str:
        module = [module]
    url = url_builder(username, repo, branch)
    return add_remote_repo(module, url)


@contextmanager
def github_repo(username=None, repo=None, module=None, branch=None, commit=None):
    importer = _add_git_repo(__create_github_url,
        username, repo, module=module, branch=branch, commit=commit)
    yield
    remove_remote_repo(importer.base_url)


def load(module_name, url='http://localhost:8000/'):
    importer = GHImporter([module_name], url)
    loader = importer.find_module(module_name)
    if loader:
        module = loader.load_module(module_name)
        if module:
            return module
    raise ImportError("Module '%s' cannot be imported from URL: '%s'" % (module_name, url) )



__all__ = [
    'GHImporter',

    'add_remote_repo',
    'remove_remote_repo',

    'remote_repo',
    'github_repo',
]
