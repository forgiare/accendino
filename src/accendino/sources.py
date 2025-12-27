import os
import shutil
import subprocess

from pathlib import Path
from zenlog import log as logging


class Source:
    ''' Generic code source '''

    def __init__(self, pkgs = {}):
        self.pkgDeps = pkgs


class LocalSource(Source):
    ''' Code source taken from a local directory that is either copied or symlinked '''

    def __init__(self, srcdir : str, do_symlink : bool = False) -> None:
        '''
            @param srcdir: source directory
            @param do_symlink: tells if the source tree must be symlinked or deep copied
        '''
        Source.__init__(self)
        self.srcdir = srcdir
        self.symlink = do_symlink

    def checkout(self, target_dir: str, _flog) -> bool:
        if os.path.exists(target_dir):
            if not self.symlink:
                if os.path.islink(target_dir):
                    return True
                logging.error(f"{target_dir} is a symlink, but we should do a hardcopy of the source tree" +
                              f" at {self.srcdir}. Please fix this by hand")
                return False

            logging.debug(f"==> refreshing dir {target_dir}")
            return True

        if self.symlink:
            logging.debug(f"==> linking {self.srcdir} to {target_dir}")
            os.symlink(os.path.abspath(self.srcdir), target_dir)
            return True

        try:
            logging.debug(f"==> copying {self.srcdir} to {target_dir}")
            shutil.copytree(src=self.srcdir, dst=target_dir)
            return True
        except Exception as e:
            logging.error(f"error copying tree: {e}")
            return False

class GitSource(Source):
    ''' Code source that is checked out from git '''

    def __init__(self, url: str, branch: str, depth: int = 1, shallow_submodules: bool = True,
                 recurse_submodules: bool = True) ->  None:
        '''
            @param url: URL of the git repo
            @param branch: branch to checkout
            @param depth: git --depth argument
            @param shallow_submodules: git --shallow-submodules argument
            @param recurse_submodules: git --recurse-submodules
        '''
        Source.__init__(self, {
            'Ubuntu|Debian': ['git'],
            'Fedora|Redhat': ['git'],
            'Windows': ['choco/git|path/git'],
        })

        self.url = url
        self.branch = branch
        self.depth = depth
        self.shallow_submodules = shallow_submodules
        self.recurse_submodules = recurse_submodules

    def checkout(self, target_dir: str, flog) -> bool:
        ''' '''
        if os.path.exists(target_dir):
            logging.debug(f"==> refreshing git dir {target_dir}")
            #cmd = ['git', 'pull']
            return True

        logging.debug(f"==> checking out repo in {target_dir}")
        cmd = ['git', 'clone', self.url, '-b', self.branch, target_dir]
        if self.depth:
            cmd += ['--depth', str(self.depth)]
        if self.shallow_submodules:
            cmd.append('--shallow-submodules')
        if self.recurse_submodules:
            cmd.append('--recurse-submodules')

        proc = subprocess.run(cmd, stdout=flog, stderr=flog)
        return proc.returncode == 0


class RemoteArchiveSource(Source):
    ''' Code source that is checked out from a remote location '''

    def __init__(self, url: str, saveAs: str = None, compression_method: str = 'guess') ->  None:
        '''
            @param url: URL of the archive repo
        '''
        Source.__init__(self, {
            'Ubuntu|Debian|Fedora|Redhat': ['curl'],
            'Windows': ['choco/curl|path/curl'],
        })

        if saveAs is None:
            pos = url.rfind("/")
            if pos == -1:
                logging.error(f'unable to extract filename from url {url}')
                raise NotImplementedError()
            self.saveAs = url[pos+1:]
        else:
            self.saveAs = saveAs

        knownCompressions = {
            'tar.gz': (['tar', 'xzf'],
                {
                    'Ubuntu|Debian|Fedora|Redhat': ['tar', 'gzip'],
                    'Windows': ['choco/7z|path/7z']
                },

            ),
            'tar': (['tar', 'xf'],
                {
                    'Ubuntu|Debian|Fedora|Redhat': ['tar'],
                    'Windows': ['choco/7zip|path/7z']
                },
            ),
            'zip': (['unzip', '-o'],
                {
                    'Ubuntu|Debian|Fedora|Redhat': ['unzip'],
                    'Windows': ['choco/7z|path/7z']
                },
            ),
            '7z': (['7z', 'x'],
                {
                    'Ubuntu|Debian|Fedora|Redhat': ['unzip'],
                    'Windows': ['choco/7z|path/7z']
                },
            ),
        }

        self.url = url
        self.compression = compression_method

        compProps = None
        if compression_method == 'guess':
            for ext, props in knownCompressions.items():
                if url.endswith('.' + ext):
                    compProps = props
                    break

            if compProps is None:
                logging.error(f'unable to guess compression method from url {url}')
                raise NotImplementedError()

        else:
            compProps = knownCompressions.get(compression_method, None)

        if compression_method and compProps is None:
            logging.error(f'unknown compression method {compression_method}')
            raise NotImplementedError()

        self.decompressCmd = None
        if compProps:
            # update native package deps
            for k, v in compProps[1].items():
                if k in self.pkgDeps:
                    self.pkgDeps[k] += v
                else:
                    self.pkgDeps[k] = [ v ]

            self.decompressCmd = compProps[0]
        else:
            if compression_method:
                logging.error(f'unknown compression method {compression_method}')
                raise NotImplementedError()

    def decompress(self, target_dir, sourcePath, flog):
        if self.decompressCmd is None:
            return True

        extractCmd = self.decompressCmd + [ str(sourcePath) ]
        logging.debug(f'running {" ".join(extractCmd)} in {target_dir}')
        proc = subprocess.run(extractCmd, cwd=target_dir, stdout=flog, stderr=flog)
        if proc.returncode != 0:
            logging.error(f'error extracting {sourcePath} in {target_dir}')
            return False
        return True


    def checkout(self, target_dir, flog) -> bool:
        archiveDir = target_dir / '..' / '..' / 'archives'
        if not os.path.exists(archiveDir):
            os.makedirs(archiveDir, exist_ok=True)

        saveAsPath = Path(archiveDir / self.saveAs).resolve()
        retrieveCmd = ['curl', '-s', '-L', self.url, '-o', str(saveAsPath)]

        if os.path.exists(saveAsPath):
            retrieveCmd += ['-z', str(saveAsPath)]

        logging.debug(f'running {" ".join(retrieveCmd)}')
        proc = subprocess.run(retrieveCmd, stdout=flog, stderr=flog)
        if proc.returncode != 0:
            logging.error(f'error retrieving {self.url}')
            return False

        return self.decompress(target_dir, saveAsPath, flog)
