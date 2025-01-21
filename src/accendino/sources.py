import os
import shutil
import subprocess

from zenlog import log as logging

class Source:
    ''' Generic code source '''


class LocalSource(Source):
    ''' Code source taken from a local directory that is either copied or symlinked '''

    def __init__(self, srcdir : str, do_symlink : bool = False) -> None:
        '''
            @param srcdir: source directory
            @param do_symlink: tells if the source tree must be symlinked or deep copied
        '''
        self.srcdir = srcdir
        self.symlink = do_symlink

    def checkout(self, target_dir: str, _flog) -> bool:
        if os.path.exists(target_dir):
            if self.symlink:
                if os.path.islink(target_dir):
                    return True
                logging.error(f"{target_dir} is a symlink, but we should do a hardcopy of the source tree" +
                              f" at {self.srcdir}. Please fix this by hand")
                return False

            logging.debug(f"   ==> refreshing dir {target_dir}")
            return True

        try:
            logging.debug(f"   ==> copying {self.srcdir} to {target_dir}")
            shutil.copytree(src=self.srcdir, dst=target_dir)
            return True
        except Exception as e:
            logging.error(f"error copying tree: {e}")
            return False

class GitSource(Source):
    ''' Code source that is checked out from git '''

    def __init__(self, url: str, branch: str, depth: int = 1, shallow_submodules: bool = False,
                 recurse_submodules: bool = False) ->  None:
        '''
            @param url: URL of the git repo
            @param branch: branch to checkout
            @param depth: git --depth argument
            @param shallow_submodules: git --shallow-submodules argument
            @param recurse_submodules: git --recurse-submodules
        '''
        self.url = url
        self.branch = branch
        self.depth = depth
        self.shallow_submodules = shallow_submodules
        self.recurse_submodules = recurse_submodules

    def checkout(self, target_dir: str, flog) -> bool:
        ''' '''
        if os.path.exists(target_dir):
            logging.debug(f"   ==> refreshing git dir {target_dir}")
            #cmd = ['git', 'pull']
            return True

        logging.debug(f"   ==> checking out repo in {target_dir}")
        cmd = ['git', 'clone', self.url, '-b', self.branch, target_dir]
        if self.depth:
            cmd += ['--depth', str(self.depth)]
        if self.shallow_submodules:
            cmd.append('--shallow-submodules')
        if self.recurse_submodules:
            cmd.append('--recurse-submodules')

        proc = subprocess.run(cmd, stdout=flog, stderr=flog)
        return proc.returncode == 0
