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

FLAGS = {
  'flag_guiding':     'Significant guiding problems',
  'flag_focus':       'Focus problems',
  'flag_ROnoise':     'Electronic readout noise problems',
}

def initdb():
  db = sqlite3.connect(DATABASE)
  SQL = '''
        CREATE TABLE Flags (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, comments TEXT, %s);
        '''
  SQL = SQL.strip()
  SQL = SQL % (','.join(FLAGS.keys()),)
  if DEBUG:
    print "initdb: SQL:\n %s" % SQL
  db.execute(SQL)
  db.commit()
  db.close()
  

class Application(tk.Frame):              
  def __init__(self, master=None):
    self.initImages()
    self.connectToDB()
    self.currentTarget = None
    tk.Frame.__init__(self, master)   
    self.grid()
    self.createWidgets()

  def initImages(self):
    pool = Pool(processes=4) 
    self.cache={}
    fitsimages = []
    print "Walking directory structure to find GROND images. This may take a moment!"
    for path, dirs, files in os.walk(sys.argv[1]):
      for f in files:
        if re.search(FITS_REGEX,f):
          fitsimages.append(os.path.join(os.path.abspath(path),f))

    for image in fitsimages:
      d = pyfits.open(image)[0].data
      fname = os.path.join(CACHE_DIR,'%s.png' % uuid.uuid4())
      #saveBitmap(outputFileName, imageData, cutLevels, size, colorMapName)
      #cutLevels=["smart", 99.5],size=300,colorMapName='gray'
      args = [fname,d,["smart", 99.5],400,'gray']
      if DEBUG:
        print "Running asnyc job astImages.saveBitmap with args=%s" % args
      pool.apply_async(IMAGE_ENGINE,args,callback=self.updateCache(image,fname))

  def updateCache(self,image,fname):
    if DEBUG:
      print "updating cache with %s=%s" % (image,fname)
    self.cache[image]=fname

  def connectToDB(self):
    if not os.path.isfile(DATABASE):
      initdb()
    self.db = sqlite3.connect(DATABASE)

  def getImages():
    
      

  def printPosition(self,widget):
    grid_info = widget.grid_info()
    print "row:", grid_info["row"], "column:", grid_info["column"] 

  def clear(self):
    [i.grid_forget() for i in self.imlabels]
    [b.grid_forget() for b in self.buttons]
    [c.grid_forget() for c in self.checkboxes]

  def createWidgets(self):
    self.imlabels = []
    col,row = 0,0
    for image in self.getImages():
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
                  
