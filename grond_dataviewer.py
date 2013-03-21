import Tkinter as tk       
from PIL import Image, ImageTk
import os
import sys
import sqlite3
import pyfits
from multiprocessing import Pool
import uuid
import re

BASEDIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0,BASEDIR)
from lib import astImages



DEBUG = True
DATABASE = os.path.join(BASEDIR,'dataviewer.db')
CACHE_DIR = os.path.join(BASEDIR,'cache')
FITS_REGEX = 'GROND_._OB_ana.fits'
IMAGE_ENGINE = astImages.saveBitmap
PLACEHOLDER_IMAGE = os.path.join(BASEDIR,'images/placeholder.png')
BANDS = 'grizJHK'

FLAGS = {
  'flag_guiding':     'Significant guiding problems',
  'flag_focus':       'Focus problems',
  'flag_ROnoise':     'Electronic readout noise problems',
}

def initdb():
  db = sqlite3.connect(DATABASE)
  SQL = '''
        CREATE TABLE Flags (id INTEGER PRIMARY KEY AUTOINCREMENT, target TEXT, comments TEXT, saved INTEGER, %s);
        '''
  SQL = SQL.strip()
  SQL = SQL % (','.join(FLAGS.keys()),)
  if DEBUG:
    print "initdb: SQL:\n %s" % SQL
  db.execute(SQL)
  db.commit()
  db.close()
  

class Application(tk.Frame):
  '''
  Creates the GROND data QA app.
  Loops (recursively) over the GROND_._OB_ana.fits images found in the CL specified
  path.
  Makes PNGs of the entire field, and presents them on a TKinter GUI. Saves the "flags"
  checkboxes to a sqlite3 database
  '''

  def __init__(self, master=None):
    self.connectToDB()
    self.initTargets()
    self.currentTarget = None
    tk.Frame.__init__(self, master)   
    self.grid()
    self.createWidgets()

  def initTargets(self):
    '''
    Finds all GROND_._OB_ana.fits files in the CL specified directory
    Gives these images to the (async) process that creates the PNGs 
    '''
    pool = Pool(processes=4) 
    self.cache={}
    fitsimages = []
    self.targets = []
    print "Walking directory structure to find GROND images. This may take a moment!"
    for path, dirs, files in os.walk(sys.argv[1]):
      for f in files:
        if re.search(FITS_REGEX,f):
          img = os.path.join(os.path.abspath(path),f)
          fitsimages.append(img)
          target = img[:re.search(FITS_REGEX,img).start()-2]
          if target not in self.targets:
            self.targets.append(target)        
    self.currentTarget = self.targets[0]
    
    for image in fitsimages:
      if IMAGE_ENGINE==astImages.saveBitmap:
       d = pyfits.open(image)[0].data
       fname = os.path.join(CACHE_DIR,'%s.png' % uuid.uuid4())
       #saveBitmap(outputFileName, imageData, cutLevels, size, colorMapName)
       #cutLevels=["smart", 99.5],size=300,colorMapName='gray'
       args = [fname,d,["smart", 99.5],400,'gray']
      if IMAGE_ENGINE==lib.ds9:
        args = []
      if DEBUG:
        print "Running asnyc job with args=%s" % args
      pool.apply_async(IMAGE_ENGINE,args,callback=self.updateCache(image,fname))

  def updateCache(self,image,fname):
    '''
    Callback function that is called whenever an async task completes.
    Updates the internal cache with {FITS_path:PNG_path}
    '''
    if DEBUG:
      print "updating cache with %s=%s" % (image,fname)
    self.cache[image]=fname

  def connectToDB(self):
    if not os.path.isfile(DATABASE):
      initdb()
    self.db = sqlite3.connect(DATABASE)

  def getImagesFromCache(self):
    '''
    Looks into the internal cache for PNGs. If not there, returns a placeholder image
    '''
    L = []
    for band in BANDS:
      ct = self.currentTarget
      currentImage = '%s/%s/GROND_%s_OB_ana.fits' % (ct,band,band)
      if currentimage in self.cache.keys():
        L.append(self.cache[currentimage])
      else:
        L.append(PLACEHOLDER_PNG)
    return L #List of PNG paths  
      

  def printPosition(self,widget):
    '''
    Print the TKinter grid position (debug purposes only)
    '''
    grid_info = widget.grid_info()
    print "row:", grid_info["row"], "column:", grid_info["column"] 

  def refresh(self):
    self.clear()
    self.createWidgets()

  def clear(self):
    [i.grid_forget() for i in self.imlabels]
    [b.grid_forget() for b in self.buttons]
    [c.grid_forget() for c in self.checkboxes]

  def createWidgets(self):
    self.imlabels = []
    col,row = 0,0
    for image in self.getImagesFromCache():
      photo = ImageTk.PhotoImage(Image.open(image))
      imlabel = tk.Label(self,image=photo)
      imlabel.image = photo # keep a reference!
      imlabel.grid(column=col,row=row)
      col += 1
      if col > 2:
        row += 1
        col = 0
      self.imlabels.append(imlabel)

    self.buttons = []
    self.checkboxes = []
    b = tk.Button(self, text='Save and Quit', command=self.quit)
    b.grid()        
    self.buttons.append(b)

    b = tk.Button(self, text="Save and continue",command=self.next)
    b.grid()
    self.buttons.append(b)
    
    b = tk.Button(self, text="Refresh page",command=self.refresh)
    b.grid()
    self.buttons.append(b)

    b = tk.Button(self, text="Previous",command=self.back)
    b.grid()
    self.buttons.append(b)
  
    c = tk.Checkbutton(self,text="Checkbutton")
    c.grid()
    self.checkboxes.append(c)

    if DEBUG:
      print "Images:"
      [self.printPosition(i) for i in self.imlabels]
      print "Buttons:"
      [self.printPosition(b) for b in self.buttons]

  def next(self):
    pass

  def back(self):
    pass


if __name__ == "__main__":
  app = Application()                       
  app.master.title('Title')    
  app.mainloop()          
                  
